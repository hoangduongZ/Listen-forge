"""The TTS seam. Everything downstream depends on this protocol, not on edge-tts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class AudioParams:
    """Container parameters of the synthesized audio.

    Assembly relies on every part sharing these so the final concat can be a stream copy
    instead of a re-encode; generated silence is rendered to match.
    """

    sample_rate: int
    channels: int
    bitrate: str


@runtime_checkable
class TTSProvider(Protocol):
    name: str
    version: str
    params: AudioParams

    async def synthesize(self, text: str, voice: str, rate: str) -> bytes:
        """Return MP3 bytes for one utterance. Must never return an empty payload."""
        ...
