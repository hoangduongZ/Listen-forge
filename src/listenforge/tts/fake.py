"""Offline TTS stand-in for tests.

Emits real, concat-compatible MP3 with the same container parameters as the live
provider, so the assembly stage is exercised for real without touching the network.
Duration scales with text length and the voice picks the tone, which makes the output
audibly distinguishable when a human checks a fixture.
"""

from __future__ import annotations

import hashlib

from ..audio.ffmpeg import FFmpeg
from .base import AudioParams

FAKE_PARAMS = AudioParams(sample_rate=24000, channels=1, bitrate="48k")

_SECONDS_PER_CHAR = 0.04
_MIN_SECONDS = 0.3
_MAX_SECONDS = 6.0


class FakeTTS:
    name = "fake"
    version = "1"
    params = FAKE_PARAMS

    def __init__(self, ffmpeg: FFmpeg) -> None:
        self._ffmpeg = ffmpeg
        self.calls: list[tuple[str, str, str]] = []

    async def synthesize(self, text: str, voice: str, rate: str) -> bytes:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Refusing to synthesize empty text.")
        self.calls.append((cleaned, voice, rate))

        seconds = min(_MAX_SECONDS, max(_MIN_SECONDS, len(cleaned) * _SECONDS_PER_CHAR))
        if rate.startswith("-"):
            seconds *= 1.3  # mimic the slow pass being longer
        digest = hashlib.sha256(voice.encode()).digest()[0]
        frequency = 180 + digest % 220

        return self._ffmpeg.render_tone(
            frequency=frequency,
            seconds=round(seconds, 3),
            params=self.params,
        )
