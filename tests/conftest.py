from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from listenforge.audio.ffmpeg import FFmpeg
from listenforge.samples import SAMPLES

VALID_LESSON = """\
---
schema_version: "1.0"
id: "001"
title: "Job Interview"
level: "B1"
topic: "career"
language: "en-US"
---

## Context

Bạn đang tham gia một buổi phỏng vấn xin việc.

## Listening

Interviewer: Could you tell me about your experience?

Candidate: Sure. I've been working with Java for two years.

## Vocabulary

- `experience` — kinh nghiệm
- `most recently` — gần đây nhất

## Notes

Focus on interview phrases.
"""

NARRATION_LESSON = """\
---
schema_version: "1.0"
id: "002"
title: "Database Problem"
level: "B2"
topic: "engineering"
language: "en-US"
---

## Context

Bạn nghe một đồng nghiệp kể về sự cố hiệu năng.

## Listening

Yesterday, I had to investigate a performance problem in our database.
The API was becoming slower as the amount of data increased.

There was one thing we missed: the index on the orders table.
"""


@pytest.fixture
def ffmpeg() -> FFmpeg:
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is not installed")
    return FFmpeg.discover()


@pytest.fixture
def lesson_dir(tmp_path: Path) -> Path:
    """An input directory holding the three shipped sample lessons."""
    directory = tmp_path / "input"
    directory.mkdir()
    for name, content in SAMPLES.items():
        (directory / name).write_text(content, encoding="utf-8")
    return directory


@pytest.fixture
def write_lesson(tmp_path: Path):
    def _write(name: str, content: str) -> Path:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    return _write
