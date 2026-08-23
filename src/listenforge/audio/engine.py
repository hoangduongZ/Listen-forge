"""Audio assembly.

Three cached tiers:

  1. one MP3 per utterance, straight from the TTS provider
  2. those joined (with an inter-line pause) into vi / en_normal / en_slow blocks
  3. the final file: context -> pause -> english -> pause -> english -> pause -> slow

`en_normal` is synthesized once and referenced twice, which removes a third of the
speech requests for the default sequence.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from ..cache import Cache, cache_key
from ..config import Config
from ..models import Lesson, Segment
from ..tts.base import AudioParams, TTSProvider
from .ffmpeg import FFmpeg

VIETNAMESE_RATE = "+0%"


@dataclass(frozen=True, slots=True)
class VoicePlan:
    vietnamese: str
    by_speaker: dict[str | None, str]

    def for_segment(self, segment: Segment) -> str:
        return self.by_speaker.get(segment.speaker) or self.by_speaker[None]


def plan_voices(lesson: Lesson, config: Config) -> VoicePlan:
    """Assign English voices by first appearance, not by hashing the speaker name.

    Hashing would let two speakers land on the same voice, defeating the whole point of
    multi-voice dialogue.
    """
    english = list(config.voices.english) or ["en-US-GuyNeural"]
    mapping: dict[str | None, str] = {None: english[0]}
    if config.voices.multi_speaker:
        for index, speaker in enumerate(lesson.speakers):
            mapping[speaker] = english[index % len(english)]
    else:
        for speaker in lesson.speakers:
            mapping[speaker] = english[0]
    return VoicePlan(vietnamese=config.voices.vietnamese, by_speaker=mapping)


class AudioEngine:
    def __init__(
        self,
        *,
        config: Config,
        tts: TTSProvider,
        cache: Cache,
        ffmpeg: FFmpeg,
    ) -> None:
        self.config = config
        self.tts = tts
        self.cache = cache
        self.ffmpeg = ffmpeg
        self.params: AudioParams = tts.params

    async def build(self, lesson: Lesson, dest_tmp: Path) -> None:
        voices = plan_voices(lesson, self.config)

        context_task = self._block(
            [Segment(speaker=None, text=lesson.context)],
            voice_for=lambda _s: voices.vietnamese,
            rate=VIETNAMESE_RATE,
            label="context",
        )
        normal_task = self._block(
            list(lesson.listening),
            voice_for=voices.for_segment,
            rate=self.config.speed.normal,
            label="normal",
        )
        slow_task = self._block(
            list(lesson.listening),
            voice_for=voices.for_segment,
            rate=self.config.speed.slow,
            label="slow",
        )
        context, english_normal, english_slow = await asyncio.gather(
            context_task, normal_task, slow_task
        )

        parts = [context, self._silence(self.config.pauses.after_context)]
        blocks = [english_normal] * max(1, self.config.repeat_normal_times) + [english_slow]
        parts.append(blocks[0])
        for block in blocks[1:]:
            parts.append(self._silence(self.config.pauses.after_english))
            parts.append(block)

        self.ffmpeg.concat_copy(parts, dest_tmp)

    async def _block(
        self,
        segments: list[Segment],
        *,
        voice_for,
        rate: str,
        label: str,
    ) -> Path:
        """Synthesize each segment, then join them with the inter-line pause."""
        pieces = await asyncio.gather(
            *(self._utterance(segment.text, voice_for(segment), rate) for segment in segments)
        )
        if len(pieces) == 1:
            return pieces[0]

        key = cache_key(
            "block",
            label,
            self.config.pauses.between_lines,
            *(piece.name for piece in pieces),
        )
        cached = self.cache.hit("block", key)
        if cached is not None:
            return cached

        gap = self._silence(self.config.pauses.between_lines)
        joined: list[Path] = []
        for index, piece in enumerate(pieces):
            if index:
                joined.append(gap)
            joined.append(piece)

        target = self.cache.path_for("block", key)
        self.ffmpeg.concat_copy(joined, target)
        return target

    async def _utterance(self, text: str, voice: str, rate: str) -> Path:
        """One cached speech segment.

        The key covers voice, rate, provider version and container parameters — leaving
        any of them out would replay stale audio after a config change.
        """
        key = cache_key(
            self.tts.name,
            self.tts.version,
            voice,
            rate,
            self.params.sample_rate,
            self.params.channels,
            self.params.bitrate,
            text,
        )
        cached = self.cache.hit("speech", key)
        if cached is not None:
            return cached
        audio = await self.tts.synthesize(text, voice, rate)
        return self.cache.store("speech", key, audio)

    def _silence(self, seconds: float) -> Path:
        seconds = max(0.05, float(seconds))
        key = cache_key(
            "silence",
            f"{seconds:.3f}",
            self.params.sample_rate,
            self.params.channels,
            self.params.bitrate,
        )
        cached = self.cache.hit("silence", key)
        if cached is not None:
            return cached
        target = self.cache.path_for("silence", key)
        self.ffmpeg.render_silence(seconds, self.params, target)
        return target

    def expected_duration(self, lesson: Lesson) -> float | None:
        """Sum of the pause durations only — speech length is unknown until synthesis."""
        pauses = self.config.pauses
        blocks = max(1, self.config.repeat_normal_times) + 1
        gaps_per_block = max(0, len(lesson.listening) - 1)
        return (
            pauses.after_context
            + pauses.after_english * (blocks - 1)
            + pauses.between_lines * gaps_per_block * blocks
        )
