"""Error types. Exit codes follow the CLI contract: 2 = path/validation, 1 = partial batch failure."""

from __future__ import annotations

from pathlib import Path

EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_INVALID = 2


class ListenForgeError(Exception):
    """Base class for every error we render to the user instead of tracebacking."""

    exit_code = EXIT_INVALID


class PathError(ListenForgeError):
    """Invalid input/output path. Messages are worded exactly as require-plan.md §13."""


class LessonError(ListenForgeError):
    """A lesson file failed to parse or validate (lesson-format-prompt.md §14)."""

    def __init__(
        self,
        source: Path | str,
        problem: str,
        *,
        lesson_id: str | None = None,
        section: str | None = None,
        line: int | None = None,
        hint: str | None = None,
    ) -> None:
        self.source = Path(source)
        self.problem = problem
        self.lesson_id = lesson_id
        self.section = section
        self.line = line
        self.hint = hint
        super().__init__(problem)

    def __str__(self) -> str:
        # §14 requires: file path, lesson id if available, section, problem.
        parts = [f"Error parsing:\n{self.source}", ""]
        if self.lesson_id:
            parts.append(f"Lesson ID: {self.lesson_id}")
        if self.section:
            parts.append(f"Section: {self.section}")
        if self.lesson_id or self.section:
            parts.append("")
        where = f" on line {self.line}" if self.line is not None else ""
        parts.append(f"{self.problem}{where}")
        if self.hint:
            parts.extend(["", self.hint])
        return "\n".join(parts)


class TTSError(ListenForgeError):
    """Speech synthesis failed."""


class AudioError(ListenForgeError):
    """ffmpeg is missing or an audio assembly step failed."""
