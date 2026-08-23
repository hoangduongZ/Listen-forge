"""Path precedence and validation — require-plan.md §3, §13, §14."""

from __future__ import annotations

from pathlib import Path

import pytest

from listenforge.errors import PathError
from listenforge.paths import (
    ensure_output_dir,
    iter_lesson_files,
    output_path_for,
    resolve_lesson_argument,
    resolve_paths,
    sanitize_stem,
    validate_input_dir,
)


def test_defaults_when_nothing_is_given():
    paths = resolve_paths(None, None)
    assert paths.input_dir == Path("./input").absolute()
    assert paths.output_dir == Path("./output").absolute()


def test_input_only_leaves_output_at_default():
    paths = resolve_paths("./lessons", None)
    assert paths.input_dir == Path("./lessons").absolute()
    assert paths.output_dir == Path("./output").absolute()


def test_output_only_leaves_input_at_default():
    paths = resolve_paths(None, "./mp3")
    assert paths.input_dir == Path("./input").absolute()
    assert paths.output_dir == Path("./mp3").absolute()


def test_both_given():
    paths = resolve_paths("./lessons", "./mp3")
    assert paths.input_dir == Path("./lessons").absolute()
    assert paths.output_dir == Path("./mp3").absolute()


def test_cli_beats_config():
    paths = resolve_paths("./cli-in", None, config_input="./cfg-in", config_output="./cfg-out")
    assert paths.input_dir == Path("./cli-in").absolute()
    assert paths.output_dir == Path("./cfg-out").absolute()


def test_absolute_paths_are_preserved():
    paths = resolve_paths("/home/user/english-lessons", "/media/sdcard/english")
    assert paths.input_dir == Path("/home/user/english-lessons")
    assert paths.output_dir == Path("/media/sdcard/english")


def test_display_paths_echo_what_the_user_typed():
    paths = resolve_paths("./lessons", "./mp3")
    assert paths.input_display == "./lessons"
    assert paths.output_display == "./mp3"


def test_missing_input_dir_message_matches_the_spec():
    with pytest.raises(PathError) as excinfo:
        validate_input_dir(Path("/definitely/not/here"), "./lessons")
    assert str(excinfo.value) == "Error: Input directory does not exist:\n./lessons"


def test_output_dir_is_created(tmp_path):
    target = tmp_path / "deep" / "nested" / "audio"
    ensure_output_dir(target, "./audio")
    assert target.is_dir()


def test_unwritable_output_dir_is_reported_up_front(tmp_path):
    """The probe runs before synthesis so a read-only card fails fast, not after minutes."""
    blocked = tmp_path / "ro"
    blocked.mkdir()
    blocked.chmod(0o500)
    try:
        with pytest.raises(PathError) as excinfo:
            ensure_output_dir(blocked / "out", "./out")
        assert "cannot be created" in str(excinfo.value)
    finally:
        blocked.chmod(0o700)


def test_iter_lesson_files_skips_dotfiles_and_appledouble(tmp_path):
    (tmp_path / "001-a.md").touch()
    (tmp_path / "002-b.md").touch()
    (tmp_path / "._001-a.md").touch()  # macOS AppleDouble sidecar on FAT/exFAT
    (tmp_path / ".DS_Store").touch()
    (tmp_path / "notes.txt").touch()

    assert [p.name for p in iter_lesson_files(tmp_path)] == ["001-a.md", "002-b.md"]


def test_output_name_is_derived_from_the_input_name(tmp_path):
    assert (
        output_path_for(Path("001-job-interview.md"), tmp_path).name
        == "001-job-interview.mp3"
    )


def test_sanitize_stem_removes_fat_hostile_characters():
    assert sanitize_stem('001:a?b*c"d<e>f|g') == "001_a_b_c_d_e_f_g"
    assert sanitize_stem("trailing.") == "trailing"


class TestLessonArgument:
    def test_bare_name_resolves_under_input(self, tmp_path):
        (tmp_path / "001-job.md").write_text("x")
        assert resolve_lesson_argument("001-job.md", tmp_path, "./input").name == "001-job.md"

    def test_md_suffix_is_optional(self, tmp_path):
        (tmp_path / "001.md").write_text("x")
        assert resolve_lesson_argument("001", tmp_path, "./input").name == "001.md"

    def test_unique_prefix_match(self, tmp_path):
        (tmp_path / "003-daily-conversation-dinner.md").write_text("x")
        found = resolve_lesson_argument("003", tmp_path, "./input")
        assert found.name == "003-daily-conversation-dinner.md"

    def test_ambiguous_prefix_is_an_error_not_a_guess(self, tmp_path):
        (tmp_path / "003-a.md").write_text("x")
        (tmp_path / "003-b.md").write_text("x")
        with pytest.raises(PathError) as excinfo:
            resolve_lesson_argument("003", tmp_path, "./input")
        assert "more than one file" in str(excinfo.value)

    def test_explicit_path_bypasses_input_dir(self, tmp_path):
        elsewhere = tmp_path / "other"
        elsewhere.mkdir()
        target = elsewhere / "005.md"
        target.write_text("x")
        found = resolve_lesson_argument(str(target), tmp_path / "input", "./input")
        assert found == target

    def test_traversal_is_rejected(self, tmp_path):
        with pytest.raises(PathError) as excinfo:
            resolve_lesson_argument("../secrets.md", tmp_path, "./input")
        assert ".." in str(excinfo.value)

    def test_missing_file_message_matches_the_spec(self, tmp_path):
        with pytest.raises(PathError) as excinfo:
            resolve_lesson_argument("001.md", tmp_path, "./lessons")
        assert str(excinfo.value) == "Error: Input file does not exist:\n./lessons/001.md"
