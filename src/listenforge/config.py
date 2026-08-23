"""Configuration. Per lesson-format-prompt.md §16 the lesson Markdown says WHAT to
learn; everything about HOW to generate audio lives here."""

from __future__ import annotations

import hashlib
import json
import os
import tomllib
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from .errors import ListenForgeError

CONFIG_FILENAME = "listenforge.toml"
ENV_PREFIX = "LISTENFORGE_"

# Two normal-speed passes, then the slow one (require-plan.md §8).
DEFAULT_REPEAT_NORMAL_TIMES = 2


@dataclass(frozen=True, slots=True)
class Pauses:
    after_context: float = 2.0
    after_english: float = 2.5
    between_lines: float = 0.6


@dataclass(frozen=True, slots=True)
class Speed:
    normal: str = "+0%"
    slow: str = "-30%"


@dataclass(frozen=True, slots=True)
class Voices:
    vietnamese: str = "vi-VN-HoaiMyNeural"
    english: tuple[str, ...] = ("en-US-GuyNeural", "en-US-AriaNeural")
    multi_speaker: bool = True


@dataclass(frozen=True, slots=True)
class TTSSettings:
    provider: str = "edge"
    concurrency: int = 4
    cache: bool = True


@dataclass(frozen=True, slots=True)
class AudioSettings:
    bitrate: str = "48k"
    sample_rate: int = 24000
    ffmpeg: str = ""  # "" -> look up on PATH
    ffprobe: str = ""


@dataclass(frozen=True, slots=True)
class PathSettings:
    input: str = "./input"
    output: str = "./output"


@dataclass(frozen=True, slots=True)
class Config:
    paths: PathSettings = field(default_factory=PathSettings)
    pauses: Pauses = field(default_factory=Pauses)
    speed: Speed = field(default_factory=Speed)
    voices: Voices = field(default_factory=Voices)
    tts: TTSSettings = field(default_factory=TTSSettings)
    audio: AudioSettings = field(default_factory=AudioSettings)
    repeat_normal_times: int = DEFAULT_REPEAT_NORMAL_TIMES
    source: Path | None = None

    def fingerprint(self) -> str:
        """Hash of every setting that changes the produced audio.

        Deliberately excludes paths and `source`: moving the output directory does not
        make an already-generated MP3 stale.
        """
        payload = {
            "pauses": asdict(self.pauses),
            "speed": asdict(self.speed),
            "voices": asdict(self.voices),
            "audio": {"bitrate": self.audio.bitrate, "sample_rate": self.audio.sample_rate},
            "provider": self.tts.provider,
            "repeat_normal_times": self.repeat_normal_times,
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


CONFIG_DIRNAME = "config"


def default_config_candidates(cwd: Path | None = None) -> list[Path]:
    cwd = cwd or Path.cwd()
    return [
        cwd / CONFIG_DIRNAME / CONFIG_FILENAME,
        cwd / CONFIG_FILENAME,
        Path.home() / ".config" / "listenforge" / "config.toml",
    ]


def load_config(explicit: Path | None = None, *, cwd: Path | None = None) -> Config:
    """Precedence: --config > ./config/listenforge.toml > ./listenforge.toml >
    ~/.config/listenforge/config.toml > defaults.

    CLI flags are layered on top of the result by the caller, so they always win.
    """
    if explicit is not None:
        explicit = Path(explicit).expanduser()
        if not explicit.is_file():
            raise ListenForgeError(f"Error: Config file does not exist:\n{explicit}")
        return _apply_env(_from_toml(explicit))

    for candidate in default_config_candidates(cwd):
        if candidate.is_file():
            return _apply_env(_from_toml(candidate))
    return _apply_env(Config())


def _from_toml(path: Path) -> Config:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ListenForgeError(f"Error: Cannot read config file:\n{path}\n{exc}") from exc

    english = data.get("voices", {}).get("english")
    if isinstance(english, str):
        english = [english]

    return Config(
        paths=PathSettings(**_pick(data, "paths", PathSettings)),
        pauses=Pauses(**_pick(data, "pauses", Pauses)),
        speed=Speed(**_pick(data, "speed", Speed)),
        voices=Voices(
            **{
                **_pick(data, "voices", Voices),
                **({"english": tuple(english)} if english else {}),
            }
        ),
        tts=TTSSettings(**_pick(data, "tts", TTSSettings)),
        audio=AudioSettings(**_pick(data, "audio", AudioSettings)),
        repeat_normal_times=int(
            data.get("repeat", {}).get("normal_times", DEFAULT_REPEAT_NORMAL_TIMES)
        ),
        source=path,
    )


def _pick(data: dict, table: str, cls: type) -> dict:
    """Take only the keys `cls` declares, coercing to the annotated scalar type."""
    section = data.get(table) or {}
    if not isinstance(section, dict):
        raise ListenForgeError(f"Error: Config table [{table}] must be a table.")
    known = {f.name: f.type for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    out = {}
    for key, value in section.items():
        if key not in known or key == "english":
            continue
        out[key] = _coerce(value, known[key])
    return out


def _coerce(value: object, annotation: object) -> object:
    text = str(annotation)
    if "bool" in text:
        return bool(value)
    if "int" in text:
        return int(value)  # type: ignore[arg-type]
    if "float" in text:
        return float(value)  # type: ignore[arg-type]
    return value


def _apply_env(config: Config) -> Config:
    def env(name: str) -> str | None:
        return os.environ.get(ENV_PREFIX + name)

    paths = config.paths
    if value := env("INPUT"):
        paths = replace(paths, input=value)
    if value := env("OUTPUT"):
        paths = replace(paths, output=value)

    audio = config.audio
    if value := env("FFMPEG"):
        audio = replace(audio, ffmpeg=value)
    if value := env("FFPROBE"):
        audio = replace(audio, ffprobe=value)

    tts = config.tts
    if value := env("CONCURRENCY"):
        tts = replace(tts, concurrency=int(value))

    return replace(config, paths=paths, audio=audio, tts=tts)
