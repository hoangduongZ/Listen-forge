"""ffmpeg discovery and invocation."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..errors import AudioError
from ..tts.base import AudioParams

MP3_ENCODER = "libmp3lame"
_INSTALL_HINT = "Install it with:\n  brew install ffmpeg"


@dataclass(frozen=True, slots=True)
class FFmpeg:
    ffmpeg: Path
    ffprobe: Path | None

    @classmethod
    def discover(cls, configured: str = "", configured_probe: str = "") -> FFmpeg:
        return cls(
            ffmpeg=_locate("ffmpeg", configured, required=True),  # type: ignore[arg-type]
            ffprobe=_locate("ffprobe", configured_probe, required=False),
        )

    def has_mp3_encoder(self) -> bool:
        result = self._run_raw([str(self.ffmpeg), "-hide_banner", "-encoders"])
        return MP3_ENCODER in result.stdout

    def require_mp3_encoder(self) -> None:
        if not self.has_mp3_encoder():
            raise AudioError(
                f"Error: This ffmpeg build has no {MP3_ENCODER} encoder, so it cannot "
                f"write MP3.\n{self.ffmpeg}\n{_INSTALL_HINT}"
            )

    def version(self) -> str:
        result = self._run_raw([str(self.ffmpeg), "-hide_banner", "-version"])
        first = result.stdout.splitlines()[0] if result.stdout else ""
        return first.strip()

    # -- assembly -------------------------------------------------------------------

    def concat_copy(self, parts: list[Path], dest: Path) -> None:
        """Join same-parameter MP3 parts with no re-encode.

        MP3 has no global container header and is self-delimiting per frame, so parts
        that share sample rate, channel count and bitrate concatenate cleanly. The
        concat *demuxer* is used rather than the concat *filter*: the filter is
        sequential, and feeding it a duplicated stream via `asplit` deadlocks the graph
        (`Buffer queue overflow, dropping`) and silently truncates audio.
        """
        if not parts:
            raise AudioError("Nothing to concatenate.")
        for part in parts:
            if not part.is_file() or part.stat().st_size == 0:
                raise AudioError(f"Audio part is missing or empty: {part}")

        with tempfile.TemporaryDirectory(prefix="listenforge-concat-") as workdir:
            listing = Path(workdir) / "parts.txt"
            listing.write_text(
                "".join(f"file '{_escape(part)}'\n" for part in parts), encoding="utf-8"
            )
            self.run(
                [
                    "-f", "concat",
                    "-safe", "0",
                    "-i", str(listing),
                    "-c", "copy",
                    "-write_xing", "1",
                    "-id3v2_version", "3",
                    "-f", "mp3",
                    str(dest),
                ]
            )

    def render_silence(self, seconds: float, params: AudioParams, dest: Path) -> None:
        """Encode `seconds` of silence with the same parameters as the speech parts.

        `-t` is mandatory: `anullsrc` is an infinite source and never reaches EOF.
        """
        layout = "mono" if params.channels == 1 else "stereo"
        self.run(
            [
                "-f", "lavfi",
                "-t", f"{seconds:.3f}",
                "-i", f"anullsrc=r={params.sample_rate}:cl={layout}",
                "-c:a", MP3_ENCODER,
                "-b:a", params.bitrate,
                "-ar", str(params.sample_rate),
                "-ac", str(params.channels),
                "-f", "mp3",
                str(dest),
            ]
        )

    def render_tone(self, frequency: int, seconds: float, params: AudioParams) -> bytes:
        """A short sine tone as MP3 bytes. Used by the offline test provider."""
        layout = "mono" if params.channels == 1 else "stereo"
        with tempfile.TemporaryDirectory(prefix="listenforge-tone-") as workdir:
            out = Path(workdir) / "tone.mp3"
            self.run(
                [
                    "-f", "lavfi",
                    "-t", f"{seconds:.3f}",
                    "-i", f"sine=frequency={frequency}:sample_rate={params.sample_rate}",
                    "-c:a", MP3_ENCODER,
                    "-b:a", params.bitrate,
                    "-ar", str(params.sample_rate),
                    "-ac", str(params.channels),
                    "-af", f"aformat=channel_layouts={layout}",
                    "-f", "mp3",
                    str(out),
                ]
            )
            return out.read_bytes()

    def duration(self, path: Path) -> float | None:
        if self.ffprobe is None:
            return None
        result = self._run_raw(
            [
                str(self.ffprobe),
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ]
        )
        try:
            return float(result.stdout.strip())
        except ValueError:
            return None

    # -- plumbing -------------------------------------------------------------------

    def run(self, args: list[str]) -> None:
        command = [str(self.ffmpeg), "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *args]
        result = self._run_raw(command)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise AudioError(f"ffmpeg failed ({result.returncode}):\n{detail}")

    @staticmethod
    def _run_raw(command: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(command, capture_output=True, text=True, check=False)
        except OSError as exc:
            raise AudioError(f"Cannot run {command[0]}: {exc}") from exc


def _locate(name: str, configured: str, *, required: bool) -> Path | None:
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_file():
            raise AudioError(f"Error: Configured {name} does not exist:\n{configured}")
        return candidate
    found = shutil.which(name)
    if found:
        return Path(found)
    if required:
        raise AudioError(f"Error: {name} was not found on PATH.\n{_INSTALL_HINT}")
    return None


def _escape(path: Path) -> str:
    # concat demuxer quoting: a single quote inside the path terminates the literal.
    return str(path.absolute()).replace("'", r"'\''")
