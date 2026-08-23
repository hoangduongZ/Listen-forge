"""edge-tts provider.

Three properties of this backend shape the code below:

* Output format is hardcoded to `audio-24khz-48kbitrate-mono-mp3` — 24 kHz mono 48 kbps
  CBR. It is not selectable, which is exactly why the assembly stage can stream-copy.
* The websocket handshake carries a `Sec-MS-GEC` token derived from the system clock, so
  a skewed clock produces persistent HTTP 403s. The error message says so out loud.
* Empty or whitespace-only text returns zero audio bytes *without raising*, and a 0-byte
  segment silently corrupts the concat. Guarded before the request goes out.
"""

from __future__ import annotations

import asyncio

from ..errors import TTSError
from .base import AudioParams

# More than a handful of concurrent connections to this endpoint earns resets and 429s.
MAX_CONCURRENCY = 5
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = 1.5

EDGE_PARAMS = AudioParams(sample_rate=24000, channels=1, bitrate="48k")


class EdgeTTS:
    name = "edge"
    params = EDGE_PARAMS

    def __init__(self, concurrency: int = 4) -> None:
        self._semaphore = asyncio.Semaphore(max(1, min(concurrency, MAX_CONCURRENCY)))
        self.version = _edge_tts_version()

    async def synthesize(self, text: str, voice: str, rate: str) -> bytes:
        cleaned = text.strip()
        if not cleaned:
            raise TTSError("Refusing to synthesize empty text (would yield a 0-byte segment).")

        import edge_tts

        last_error: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            async with self._semaphore:
                try:
                    audio = await self._stream(edge_tts, cleaned, voice, rate)
                except Exception as exc:  # noqa: BLE001 - re-raised as TTSError below
                    last_error = exc
                    if _is_forbidden(exc):
                        raise TTSError(_forbidden_message(exc)) from exc
                else:
                    if audio:
                        return audio
                    last_error = TTSError(
                        f"Voice {voice!r} returned no audio for: {cleaned[:60]!r}"
                    )
            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(_BACKOFF_SECONDS * attempt)

        raise TTSError(
            f"Speech synthesis failed after {_MAX_ATTEMPTS} attempts "
            f"(voice={voice}, rate={rate}): {last_error}"
        ) from last_error

    @staticmethod
    async def _stream(edge_tts, text: str, voice: str, rate: str) -> bytes:
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        chunks = bytearray()
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio" and chunk.get("data"):
                chunks.extend(chunk["data"])
        return bytes(chunks)


async def list_voices() -> list[dict]:
    import edge_tts

    return await edge_tts.list_voices()


def _edge_tts_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("edge-tts")
    except PackageNotFoundError:  # pragma: no cover - installed by definition
        return "unknown"


def _is_forbidden(exc: Exception) -> bool:
    status = getattr(exc, "status", None)
    return status == 403 or "403" in str(exc)


def _forbidden_message(exc: Exception) -> str:
    return (
        "The speech endpoint rejected the request (HTTP 403).\n"
        "Its access token is derived from the system clock, so the usual cause is a "
        "clock that is off.\n"
        "Check your system date/time, then retry.\n"
        f"Underlying error: {exc}"
    )
