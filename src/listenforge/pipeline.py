"""Lesson -> MP3 orchestration, behind a protocol so the CLI can be exercised without
speech synthesis or audio tooling."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from .audio.engine import AudioEngine
from .audio.ffmpeg import FFmpeg
from .audio.tags import write_tags
from .cache import Cache
from .config import Config
from .errors import ListenForgeError
from .io.atomic import atomic_path
from .models import Lesson
from .tts.base import TTSProvider


class Outcome(str, Enum):
    GENERATED = "GENERATED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class Result:
    lesson_file: Path
    output_file: Path
    outcome: Outcome
    detail: str = ""
    lesson: Lesson | None = None


class Pipeline(Protocol):
    async def generate(self, lesson: Lesson, dest: Path) -> None: ...


class RealPipeline:
    def __init__(
        self, *, config: Config, tts: TTSProvider, cache: Cache, ffmpeg: FFmpeg
    ) -> None:
        self.config = config
        self.cache = cache
        self.engine = AudioEngine(config=config, tts=tts, cache=cache, ffmpeg=ffmpeg)

    async def generate(self, lesson: Lesson, dest: Path) -> None:
        with atomic_path(dest, suffix=".mp3") as tmp:
            await self.engine.build(lesson, tmp)
            write_tags(tmp, lesson.meta)


class StubPipeline:
    """Writes a fixed, tiny MP3. Lets path handling, --force, skip logic and exit codes
    be tested with no network and no ffmpeg."""

    # A single silent MPEG-1 Layer III frame: enough to be a real, non-empty file.
    _FRAME = bytes([0xFF, 0xFB, 0x10, 0xC4]) + b"\x00" * 100

    def __init__(self) -> None:
        self.generated: list[Path] = []

    async def generate(self, lesson: Lesson, dest: Path) -> None:
        await asyncio.sleep(0)
        with atomic_path(dest, suffix=".mp3") as tmp:
            tmp.write_bytes(self._FRAME * 8)
        self.generated.append(dest)


async def run_one(
    pipeline: Pipeline,
    cache: Cache,
    config: Config,
    lesson: Lesson,
    lesson_file: Path,
    output_file: Path,
    *,
    force: bool,
) -> Result:
    lesson_hash = lesson.content_hash()
    fingerprint = config.fingerprint()

    if output_file.exists() and not force:
        if not cache.is_stale(output_file, lesson_hash, fingerprint):
            return Result(
                lesson_file, output_file, Outcome.SKIPPED, "already exists", lesson
            )

    try:
        await pipeline.generate(lesson, output_file)
    except ListenForgeError as exc:
        return Result(lesson_file, output_file, Outcome.FAILED, str(exc), lesson)

    cache.record(output_file, lesson_hash, fingerprint)
    return Result(lesson_file, output_file, Outcome.GENERATED, "", lesson)
