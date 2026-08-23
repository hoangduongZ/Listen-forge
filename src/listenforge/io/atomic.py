"""Atomic file publication that survives writing onto removable media.

`os.replace` is documented to fail when source and destination are on different
filesystems (EXDEV). Generating straight onto an SD card is an explicitly supported
workflow (require-plan.md §12, §15), so the temp file must be created *next to the
destination* — never in the cache directory.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

# mkstemp creates 0600. Left alone, every generated MP3 would be owner-readable only —
# invisible on FAT (mode comes from mount options) and a real problem everywhere else.
_TARGET_MODE = 0o644


@contextlib.contextmanager
def atomic_path(dest: Path, *, suffix: str = ".tmp") -> Iterator[Path]:
    """Yield a temp path adjacent to `dest`; on clean exit, move it into place."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.", suffix=suffix)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        yield tmp
        if not tmp.exists():
            raise OSError(f"nothing was written to {tmp}")
        _chmod_best_effort(tmp)
        os.replace(tmp, dest)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def atomic_write_bytes(dest: Path, data: bytes) -> None:
    with atomic_path(dest) as tmp:
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())


def _chmod_best_effort(path: Path) -> None:
    umask = _current_umask()
    with contextlib.suppress(OSError):  # FAT/exFAT can raise EPERM here
        os.chmod(path, _TARGET_MODE & ~umask)


def _current_umask() -> int:
    previous = os.umask(0o022)
    os.umask(previous)
    return previous
