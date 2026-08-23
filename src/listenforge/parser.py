"""Markdown -> Lesson. Strict and deterministic; no fuzzy section detection
(lesson-format-prompt.md §11)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .errors import LessonError
from .models import (
    CONTEXT,
    KNOWN_SECTIONS,
    LEVELS,
    LISTENING,
    NOTES,
    SUPPORTED_SCHEMA_VERSIONS,
    VOCABULARY,
    Lesson,
    LessonMeta,
    Segment,
    VocabItem,
)

_FRONTMATTER_FENCE = re.compile(r"^---\s*$")
_SECTION_HEADING = re.compile(r"^##\s+(?P<name>.+?)\s*$")
_ANY_HEADING = re.compile(r"^#{1,6}\s+")

# Legacy bracket markers from require-plan.md §6. We detect them only to produce a
# useful error — §11 forbids silently accepting them as aliases.
_LEGACY_MARKER = re.compile(r"^\[(CONTEXT_VI|ENGLISH|VOCABULARY)\]\s*$", re.MULTILINE)

# Speaker labels must be anchored tightly. A loose `^(\w+):` matches narration like
# "There's one thing: the API is slow." and would split it into a bogus speaker.
_SPEAKER = re.compile(r"^(?P<label>[A-Z][\w .'\-]{0,30}):[ \t]+(?P<text>\S.*)$")

_VOCAB_LINE = re.compile(
    r"^[-*]\s+(?P<phrase>.+?)\s+(?:—|–)\s+(?P<meaning>.+?)\s*$"
)

_REQUIRED_META = ("schema_version", "id", "title", "level", "topic", "language")


def strip_markdown(text: str) -> str:
    """Remove inline formatting. §12 forbids sending `**` or `_` to TTS."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    return text


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()


def parse_lesson_file(path: Path) -> Lesson:
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise LessonError(path, f"File is not valid UTF-8: {exc}") from exc
    except OSError as exc:
        raise LessonError(path, f"Cannot read file: {exc}") from exc
    return parse_lesson(raw, path)


def parse_lesson(raw: str, source: Path) -> Lesson:
    meta_block, body, body_offset = _split_frontmatter(raw, source)
    meta = _parse_meta(meta_block, source)
    sections = _split_sections(body, body_offset, source, meta.id)

    context = _require_section(sections, CONTEXT, source, meta.id)
    listening_raw = _require_section(sections, LISTENING, source, meta.id)

    listening = _parse_listening(listening_raw, source, meta.id)
    vocabulary = _parse_vocabulary(sections.get(VOCABULARY), source, meta.id)
    notes_raw = sections.get(NOTES)
    notes = _paragraph_text(notes_raw[0]) if notes_raw and notes_raw[0].strip() else None

    return Lesson(
        meta=meta,
        source_path=source,
        context=_paragraph_text(context),
        listening=listening,
        vocabulary=vocabulary,
        notes=notes,
    )


def _split_frontmatter(raw: str, source: Path) -> tuple[str, str, int]:
    lines = raw.splitlines()
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start >= len(lines) or not _FRONTMATTER_FENCE.match(lines[start]):
        hint = None
        if _LEGACY_MARKER.search(raw):
            hint = _legacy_hint()
        raise LessonError(
            source,
            "Missing YAML front matter. The file must start with a '---' fence.",
            hint=hint,
        )
    for index in range(start + 1, len(lines)):
        if _FRONTMATTER_FENCE.match(lines[index]):
            meta_block = "\n".join(lines[start + 1 : index])
            body = "\n".join(lines[index + 1 :])
            return meta_block, body, index + 2  # 1-based line number of first body line
    raise LessonError(source, "YAML front matter is not closed by a '---' fence.")


def _parse_meta(block: str, source: Path) -> LessonMeta:
    try:
        data = yaml.safe_load(block) or {}
    except yaml.YAMLError as exc:
        raise LessonError(source, f"Front matter is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise LessonError(source, "Front matter must be a YAML mapping.")

    lesson_id = data.get("id")
    lesson_id = str(lesson_id).strip() if lesson_id is not None else None

    missing = [key for key in _REQUIRED_META if not str(data.get(key) or "").strip()]
    if missing:
        raise LessonError(
            source,
            f"Front matter is missing required field(s): {', '.join(missing)}",
            lesson_id=lesson_id,
        )

    values = {key: str(data[key]).strip() for key in _REQUIRED_META}

    if values["schema_version"] not in SUPPORTED_SCHEMA_VERSIONS:
        raise LessonError(
            source,
            f"Unsupported schema_version {values['schema_version']!r}. "
            f"Supported: {', '.join(SUPPORTED_SCHEMA_VERSIONS)}",
            lesson_id=lesson_id,
        )
    if values["level"] not in LEVELS:
        raise LessonError(
            source,
            f"Invalid level {values['level']!r}. Allowed: {', '.join(LEVELS)}",
            lesson_id=lesson_id,
        )
    # §2: ids must not contain path separators and must never reach a shell or a path join
    # unchecked.
    if "/" in values["id"] or "\\" in values["id"] or values["id"] in {".", ".."}:
        raise LessonError(
            source,
            f"Lesson id {values['id']!r} must not contain path separators.",
            lesson_id=lesson_id,
        )

    return LessonMeta(**values)


def _split_sections(
    body: str, offset: int, source: Path, lesson_id: str
) -> dict[str, tuple[str, int]]:
    """Return {section_name: (text, first_line_number)}.

    Unknown `##` headings are an error, not something to skip: §11 explicitly rejects
    treating `## Situation` / `## English` / `## Words` as equivalents.
    """
    sections: dict[str, tuple[str, int]] = {}
    current: str | None = None
    buffer: list[str] = []
    start_line = offset
    lines = body.splitlines()

    def flush() -> None:
        if current is not None:
            sections[current] = ("\n".join(buffer), start_line)

    for index, line in enumerate(lines):
        heading = _SECTION_HEADING.match(line)
        if heading:
            name = heading.group("name").strip()
            if name not in KNOWN_SECTIONS:
                raise LessonError(
                    source,
                    f"Unknown section '## {name}'. Allowed: "
                    + ", ".join(f"## {s}" for s in KNOWN_SECTIONS),
                    lesson_id=lesson_id,
                    line=offset + index,
                    hint="Aliases are not accepted; see lesson-format-prompt.md §11.",
                )
            if name in sections:
                raise LessonError(
                    source,
                    f"Duplicate section '## {name}'.",
                    lesson_id=lesson_id,
                    line=offset + index,
                )
            flush()
            current = name
            buffer = []
            start_line = offset + index + 1
            continue
        if current is None and _ANY_HEADING.match(line):
            raise LessonError(
                source,
                f"Sections must use '## ' headings, found {line.strip()!r}.",
                lesson_id=lesson_id,
                line=offset + index,
            )
        if current is None:
            if line.strip():
                hint = _legacy_hint() if _LEGACY_MARKER.match(line) else None
                raise LessonError(
                    source,
                    "Content found before the first '## ' section heading.",
                    lesson_id=lesson_id,
                    line=offset + index,
                    hint=hint,
                )
            continue
        buffer.append(line)
    flush()
    return sections


def _legacy_hint() -> str:
    return (
        "This file appears to use the legacy [CONTEXT_VI] / [ENGLISH] / [VOCABULARY]\n"
        "markers. ListenForge implements schema_version 1.0 only — convert them to\n"
        "'## Context', '## Listening' and '## Vocabulary' with YAML front matter."
    )


def _require_section(
    sections: dict[str, tuple[str, int]], name: str, source: Path, lesson_id: str
) -> str:
    entry = sections.get(name)
    if entry is None:
        raise LessonError(
            source,
            f"Missing required section: {name}",
            lesson_id=lesson_id,
            section=name,
        )
    text, line = entry
    if not text.strip():  # §13: required sections must not be empty
        raise LessonError(
            source,
            f"Section '{name}' is empty.",
            lesson_id=lesson_id,
            section=name,
            line=line,
        )
    return text


def _paragraphs(text: str) -> list[str]:
    return [block for block in re.split(r"\n\s*\n", text.strip()) if block.strip()]


def _paragraph_text(text: str) -> str:
    """Preserve paragraph boundaries, normalize whitespace within them (§3)."""
    out = []
    for block in _paragraphs(text):
        lines = [_normalize_whitespace(strip_markdown(line)) for line in block.splitlines()]
        out.append(" ".join(part for part in lines if part))
    return "\n\n".join(out)


def _parse_listening(text: str, source: Path, lesson_id: str) -> tuple[Segment, ...]:
    blocks = _paragraphs(text)
    candidates: list[tuple[str | None, str]] = []
    for block in blocks:
        cleaned = strip_markdown(block)  # strip **Interviewer:** before matching (§12)
        lines = [line for line in cleaned.splitlines() if line.strip()]
        joined = " ".join(_normalize_whitespace(line) for line in lines)
        match = _SPEAKER.match(joined)
        if match and not re.search(r"[.!?]", match.group("label")):
            candidates.append((match.group("label").strip(), match.group("text").strip()))
        else:
            candidates.append((None, joined))

    labelled = [item for item in candidates if item[0] is not None]
    distinct = {item[0] for item in labelled}
    # Treat as dialogue only when the evidence is strong: two distinct speakers, or every
    # paragraph carries a label. A single label on one of many paragraphs is far more
    # likely a false positive on narration than a real speaker.
    is_dialogue = len(distinct) >= 2 or (labelled and len(labelled) == len(candidates))

    if is_dialogue:
        segments = tuple(Segment(speaker=s, text=t) for s, t in candidates)
    else:
        segments = tuple(
            Segment(speaker=None, text=text_)
            for _, text_ in ((None, block) for block in _paragraphs(_paragraph_text(text)))
        )

    if not any(segment.text.strip() for segment in segments):
        raise LessonError(
            source,
            "Section 'Listening' has no speakable content.",
            lesson_id=lesson_id,
            section=LISTENING,
        )
    return segments


def _parse_vocabulary(
    entry: tuple[str, int] | None, source: Path, lesson_id: str
) -> tuple[VocabItem, ...]:
    if entry is None:
        return ()
    text, start_line = entry
    items: list[VocabItem] = []
    for index, line in enumerate(text.splitlines()):
        if not line.strip():
            continue
        match = _VOCAB_LINE.match(line.strip())
        if not match:
            raise LessonError(
                source,
                "Invalid vocabulary item",
                lesson_id=lesson_id,
                section=VOCABULARY,
                line=start_line + index,
                hint="Expected:\n- `phrase` — meaning",
            )
        items.append(
            VocabItem(
                phrase=_normalize_whitespace(strip_markdown(match.group("phrase"))),
                meaning_vi=_normalize_whitespace(strip_markdown(match.group("meaning"))),
            )
        )
    return tuple(items)
