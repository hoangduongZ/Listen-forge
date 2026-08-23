"""Path resolution and validation.

The effective paths are, per require-plan.md §14:
    INPUT  = --input  if provided, otherwise the config value, otherwise ./input
    OUTPUT = --output if provided, otherwise the config value, otherwise ./output

Every command routes through `resolve_paths` so the rule can never drift between them.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .errors import PathError

DEFAULT_INPUT = "./input"
DEFAULT_OUTPUT = "./output"
LESSON_SUFFIX = ".md"
AUDIO_SUFFIX = ".mp3"

# FAT/exFAT reject these outright; a microSD card is an explicitly supported target.
_UNSAFE_FILENAME_CHARS = re.compile(r'[:?*"<>|\\\x00-\x1f]')


@dataclass(frozen=True, slots=True)
class ResolvedPaths:
    input_dir: Path
    output_dir: Path
    input_display: str
    output_display: str


def resolve_paths(
    cli_input: str | None,
    cli_output: str | None,
    *,
    config_input: str = DEFAULT_INPUT,
    config_output: str = DEFAULT_OUTPUT,
) -> ResolvedPaths:
    raw_input = cli_input or config_input or DEFAULT_INPUT
    raw_output = cli_output or config_output or DEFAULT_OUTPUT
    return ResolvedPaths(
        input_dir=_expand(raw_input),
        output_dir=_expand(raw_output),
        # Echo paths back the way the user typed them; "./lessons" is more useful in an
        # error than its absolute form.
        input_display=raw_input,
        output_display=raw_output,
    )


def _expand(raw: str) -> Path:
    return Path(raw).expanduser().absolute()


def validate_input_dir(path: Path, display: str) -> None:
    if not path.exists():
        raise PathError(f"Error: Input directory does not exist:\n{display}")
    if not path.is_dir():
        raise PathError(f"Error: Input path is not a directory:\n{display}")


def validate_input_file(path: Path, display: str) -> None:
    if not path.exists():
        raise PathError(f"Error: Input file does not exist:\n{display}")
    if not path.is_file():
        raise PathError(f"Error: Input path is not a file:\n{display}")


def ensure_output_dir(path: Path, display: str) -> None:
    """Create the output directory when possible, then prove it is actually writable.

    The write probe runs up front on purpose: a read-only mount (macOS mounts NTFS
    read-only) or a full card would otherwise fail only after minutes of synthesis.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PathError(
            f"Error: Output directory cannot be created:\n{display}\n{exc.strerror or exc}"
        ) from exc
    if not path.is_dir():
        raise PathError(f"Error: Output path is not a directory:\n{display}")
    probe = path / ".listenforge-write-test"
    try:
        probe.touch()
        probe.unlink()
    except OSError as exc:
        raise PathError(
            f"Error: Output directory is not writable:\n{display}\n{exc.strerror or exc}"
        ) from exc


def iter_lesson_files(input_dir: Path) -> list[Path]:
    """Lesson files in the directory, sorted, dotfiles excluded.

    Filtering `.*` explicitly matters: macOS writes AppleDouble sidecars (`._001.md`)
    onto FAT/exFAT volumes, and a bare `*.md` glob would try to parse them as lessons.
    """
    found = [
        entry
        for entry in input_dir.iterdir()
        if entry.is_file()
        and not entry.name.startswith(".")
        and entry.suffix.lower() == LESSON_SUFFIX
    ]
    return sorted(found, key=lambda p: p.name)


def resolve_lesson_argument(argument: str, input_dir: Path, input_display: str) -> Path:
    """Interpret the FILE argument of `generate`.

    The spec does not define this, so the rules are explicit:
      * an absolute path, or one containing a separator, is used as given (--input ignored)
      * a bare name is resolved under INPUT
      * the `.md` suffix is optional
      * a bare name may also be the numeric prefix of exactly one lesson, so `003`
        finds `003-daily-conversation-dinner.md`; an ambiguous prefix is an error
        rather than an arbitrary pick
      * `..` traversal is rejected (lesson-format-prompt.md §2)
    """
    raw = argument.strip()
    if not raw:
        raise PathError("Error: No lesson file given.")

    candidate = Path(raw).expanduser()
    if candidate.is_absolute() or os.sep in raw or (os.altsep and os.altsep in raw):
        base = candidate.absolute()
        display = raw
    else:
        if ".." in Path(raw).parts:
            raise PathError(f"Error: Lesson name must not contain '..':\n{raw}")
        base = input_dir / raw
        display = f"{input_display.rstrip('/')}/{raw}"

    for path in (base, base.with_name(base.name + LESSON_SUFFIX)):
        if path.is_file():
            return path

    # Fall back to a unique prefix match, e.g. "003" -> "003-daily-conversation-dinner.md".
    if base.parent.is_dir():
        stem = base.name
        matches = [
            candidate
            for candidate in iter_lesson_files(base.parent)
            if candidate.stem == stem or candidate.stem.startswith(stem + "-")
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            listing = "\n".join(f"  {m.name}" for m in matches)
            raise PathError(
                f"Error: Lesson name {raw!r} matches more than one file:\n{listing}"
            )

    # Nothing matched: report the form the user actually asked for.
    validate_input_file(base, display)
    raise PathError(f"Error: Input file does not exist:\n{display}")


def sanitize_stem(stem: str) -> str:
    """Make a filename safe for FAT/exFAT without changing it on sane filesystems."""
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", stem).rstrip(" .")
    return cleaned or "lesson"


def output_path_for(lesson_file: Path, output_dir: Path) -> Path:
    """`001-job-interview.md` -> `<output>/001-job-interview.mp3` (§7)."""
    return output_dir / (sanitize_stem(lesson_file.stem) + AUDIO_SUFFIX)
