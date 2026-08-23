"""Content-addressed cache for synthesized speech, plus the staleness manifest.

Two separate stores with two different homes on purpose:

* Speech segments and rendered silence live under the user cache directory. Putting them
  next to the output would churn writes on slow removable media.
* The manifest maps an absolute output path to the lesson + config it was built from,
  which lets an *edited* lesson be detected as stale — something a plain
  does-the-file-exist check cannot do.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_cache_dir

from .io.atomic import atomic_write_bytes

APP_NAME = "listenforge"
_MANIFEST_NAME = "manifest.json"


def default_cache_root() -> Path:
    return Path(user_cache_dir(APP_NAME))


def cache_key(*parts: object) -> str:
    blob = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:40]


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    lesson_hash: str
    config_fingerprint: str


class Cache:
    def __init__(self, root: Path | None = None, *, enabled: bool = True) -> None:
        self.root = root or default_cache_root()
        self.enabled = enabled
        self._manifest: dict[str, dict[str, str]] | None = None

    # -- blobs ----------------------------------------------------------------------

    def path_for(self, kind: str, key: str, suffix: str = ".mp3") -> Path:
        # Shard by the first two hex chars to keep directories small.
        directory = self.root / kind / key[:2]
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{key}{suffix}"

    def store(self, kind: str, key: str, data: bytes, suffix: str = ".mp3") -> Path:
        path = self.path_for(kind, key, suffix)
        if not (self.enabled and path.is_file() and path.stat().st_size > 0):
            atomic_write_bytes(path, data)
        return path

    def hit(self, kind: str, key: str, suffix: str = ".mp3") -> Path | None:
        if not self.enabled:
            return None
        path = self.path_for(kind, key, suffix)
        if path.is_file() and path.stat().st_size > 0:
            return path
        return None

    def clear_speech(self) -> int:
        """Drop cached speech. Reached only via --refresh-tts, never via --force."""
        removed = 0
        for kind in ("speech", "block"):
            directory = self.root / kind
            if not directory.is_dir():
                continue
            for path in directory.rglob("*.mp3"):
                path.unlink(missing_ok=True)
                removed += 1
        return removed

    # -- manifest -------------------------------------------------------------------

    @property
    def manifest_path(self) -> Path:
        return self.root / _MANIFEST_NAME

    def _load_manifest(self) -> dict[str, dict[str, str]]:
        if self._manifest is None:
            try:
                raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                self._manifest = raw if isinstance(raw, dict) else {}
            except (OSError, json.JSONDecodeError):
                self._manifest = {}
        return self._manifest

    def get_entry(self, output_path: Path) -> ManifestEntry | None:
        record = self._load_manifest().get(str(output_path.absolute()))
        if not record:
            return None
        try:
            return ManifestEntry(record["lesson_hash"], record["config_fingerprint"])
        except KeyError:
            return None

    def record(self, output_path: Path, lesson_hash: str, config_fingerprint: str) -> None:
        manifest = self._load_manifest()
        manifest[str(output_path.absolute())] = {
            "lesson_hash": lesson_hash,
            "config_fingerprint": config_fingerprint,
        }
        self.flush()

    def flush(self) -> None:
        if self._manifest is None:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(
            self.manifest_path,
            json.dumps(self._manifest, indent=2, sort_keys=True).encode("utf-8"),
        )

    def is_stale(self, output_path: Path, lesson_hash: str, config_fingerprint: str) -> bool:
        """True when the output exists but was built from different content or settings.

        An unknown output is *not* stale: it predates the manifest, and claiming
        staleness would force a surprise rebuild of everything on first run.
        """
        entry = self.get_entry(output_path)
        if entry is None:
            return False
        return (
            entry.lesson_hash != lesson_hash
            or entry.config_fingerprint != config_fingerprint
        )
