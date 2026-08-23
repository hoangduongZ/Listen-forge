"""The validated lesson model. Downstream stages consume this, never raw Markdown
(lesson-format-prompt.md §15, §17)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
SUPPORTED_SCHEMA_VERSIONS = ("1.0",)

CONTEXT = "Context"
LISTENING = "Listening"
VOCABULARY = "Vocabulary"
NOTES = "Notes"
KNOWN_SECTIONS = (CONTEXT, LISTENING, VOCABULARY, NOTES)


@dataclass(frozen=True, slots=True)
class LessonMeta:
    schema_version: str
    id: str
    title: str
    level: str
    topic: str
    language: str


@dataclass(frozen=True, slots=True)
class Segment:
    """One paragraph of the Listening section. `speaker` is None for narration (§6)."""

    speaker: str | None
    text: str


@dataclass(frozen=True, slots=True)
class VocabItem:
    phrase: str
    meaning_vi: str


@dataclass(frozen=True, slots=True)
class Lesson:
    meta: LessonMeta
    source_path: Path
    context: str
    listening: tuple[Segment, ...]
    vocabulary: tuple[VocabItem, ...] = ()
    notes: str | None = None

    @property
    def speakers(self) -> tuple[str, ...]:
        """Distinct speakers in **first-appearance order**.

        Order matters: voice assignment indexes into this tuple. Hashing speaker names
        instead would let two speakers collide onto the same voice — the exact outcome
        multi-voice output exists to prevent.
        """
        seen: dict[str, None] = {}
        for segment in self.listening:
            if segment.speaker is not None:
                seen.setdefault(segment.speaker, None)
        return tuple(seen)

    @property
    def is_dialogue(self) -> bool:
        return bool(self.speakers)

    def content_hash(self) -> str:
        """Stable hash of everything that affects the audio. Drives staleness detection."""
        payload = json.dumps(
            {
                "schema_version": self.meta.schema_version,
                "id": self.meta.id,
                "title": self.meta.title,
                "language": self.meta.language,
                "context": self.context,
                "listening": [[s.speaker, s.text] for s in self.listening],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
