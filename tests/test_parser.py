from __future__ import annotations

import pytest

from listenforge.errors import LessonError
from listenforge.parser import parse_lesson, strip_markdown
from tests.conftest import NARRATION_LESSON, VALID_LESSON


def parse(content: str, tmp_path):
    return parse_lesson(content, tmp_path / "lesson.md")


def test_parses_dialogue_lesson(tmp_path):
    lesson = parse(VALID_LESSON, tmp_path)

    assert lesson.meta.id == "001"
    assert lesson.meta.level == "B1"
    assert lesson.meta.language == "en-US"
    assert lesson.notes == "Focus on interview phrases."
    assert lesson.is_dialogue
    assert lesson.speakers == ("Interviewer", "Candidate")
    assert [s.speaker for s in lesson.listening] == ["Interviewer", "Candidate"]
    assert lesson.listening[0].text == "Could you tell me about your experience?"
    assert len(lesson.vocabulary) == 2
    assert lesson.vocabulary[0].phrase == "experience"
    assert lesson.vocabulary[0].meaning_vi == "kinh nghiệm"


def test_speakers_are_in_first_appearance_order(tmp_path):
    """Voice assignment indexes into this tuple, so the order is load-bearing."""
    content = VALID_LESSON.replace(
        "Interviewer: Could you tell me about your experience?",
        "Candidate: I applied last week.",
    )
    lesson = parse(content, tmp_path)
    assert lesson.speakers == ("Candidate",)


def test_narration_is_not_split_into_speakers(tmp_path):
    """'There was one thing we missed: ...' must not become a speaker label."""
    lesson = parse(NARRATION_LESSON, tmp_path)

    assert not lesson.is_dialogue
    assert lesson.speakers == ()
    assert len(lesson.listening) == 2
    assert all(segment.speaker is None for segment in lesson.listening)
    assert "one thing we missed" in lesson.listening[1].text


def test_paragraph_lines_are_joined_and_whitespace_normalized(tmp_path):
    lesson = parse(NARRATION_LESSON, tmp_path)
    assert "database. The API" in lesson.listening[0].text


def test_markdown_speaker_labels_are_stripped(tmp_path):
    content = VALID_LESSON.replace(
        "Interviewer: Could you tell me about your experience?",
        "**Interviewer:** Could you tell me about your experience?",
    ).replace("Candidate: Sure.", "_Candidate:_ Sure.")
    lesson = parse(content, tmp_path)

    assert lesson.speakers == ("Interviewer", "Candidate")
    # §12: markers must never reach TTS.
    assert all("*" not in s.text and "_" not in s.text for s in lesson.listening)


def test_strip_markdown_leaves_intraword_punctuation_alone():
    assert strip_markdown("**bold** and `code`") == "bold and code"
    assert strip_markdown("snake_case_name stays") == "snake_case_name stays"


def test_vocabulary_is_optional(tmp_path):
    content = VALID_LESSON.split("## Vocabulary")[0]
    lesson = parse(content, tmp_path)
    assert lesson.vocabulary == ()
    assert lesson.notes is None


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda c: c.replace('schema_version: "1.0"\n', ""), "schema_version"),
        (lambda c: c.replace('level: "B1"', 'level: "Z9"'), "Invalid level"),
        (lambda c: c.replace('schema_version: "1.0"', 'schema_version: "9.9"'),
         "Unsupported schema_version"),
        (lambda c: c.replace("## Listening", "## English"), "Unknown section"),
        (lambda c: c.replace('id: "001"', 'id: "../etc"'), "path separators"),
    ],
)
def test_invalid_front_matter_and_sections(tmp_path, mutate, expected):
    with pytest.raises(LessonError) as excinfo:
        parse(mutate(VALID_LESSON), tmp_path)
    assert expected in str(excinfo.value)


def test_missing_required_section(tmp_path):
    content = VALID_LESSON.replace("## Listening", "## Vocabulary", 1)
    with pytest.raises(LessonError) as excinfo:
        parse(content, tmp_path)
    assert "Duplicate section" in str(excinfo.value) or "Missing required section" in str(
        excinfo.value
    )


def test_empty_required_section_is_rejected(tmp_path):
    content = VALID_LESSON.replace(
        "Bạn đang tham gia một buổi phỏng vấn xin việc.", ""
    )
    with pytest.raises(LessonError) as excinfo:
        parse(content, tmp_path)
    assert "empty" in str(excinfo.value)


def test_missing_front_matter(tmp_path):
    with pytest.raises(LessonError) as excinfo:
        parse("## Context\n\nHello\n\n## Listening\n\nHi\n", tmp_path)
    assert "front matter" in str(excinfo.value)


def test_legacy_bracket_format_gets_a_pointed_error(tmp_path):
    """require-plan.md §6 shows this older dialect; §11 of the format spec forbids
    silently accepting it, so the error must say what to do instead."""
    legacy = "[CONTEXT_VI]\n\nXin chào.\n\n[ENGLISH]\n\nHello.\n"
    with pytest.raises(LessonError) as excinfo:
        parse(legacy, tmp_path)
    message = str(excinfo.value)
    assert "[CONTEXT_VI]" in message
    assert "## Context" in message


def test_invalid_vocabulary_item_reports_its_line(tmp_path):
    content = VALID_LESSON.replace("- `experience` — kinh nghiệm", "experience = kinh nghiệm")
    with pytest.raises(LessonError) as excinfo:
        parse(content, tmp_path)
    error = excinfo.value
    assert error.section == "Vocabulary"
    assert error.line is not None
    assert "Invalid vocabulary item" in str(error)


def test_content_hash_changes_with_listening_but_not_with_notes(tmp_path):
    base = parse(VALID_LESSON, tmp_path)
    notes_changed = parse(
        VALID_LESSON.replace("Focus on interview phrases.", "Different note."), tmp_path
    )
    listening_changed = parse(
        VALID_LESSON.replace("for two years", "for five years"), tmp_path
    )

    assert base.content_hash() == notes_changed.content_hash()
    assert base.content_hash() != listening_changed.content_hash()
