"""ListenForge command line interface.

Every command resolves paths through the same helper, so the rule in require-plan.md §14
holds for all of them (and for anything added later):

    INPUT  = --input  if provided, otherwise config, otherwise ./input
    OUTPUT = --output if provided, otherwise config, otherwise ./output
"""

from __future__ import annotations

import asyncio
import json as jsonlib
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from . import samples
from .audio.ffmpeg import FFmpeg
from .cache import Cache
from .config import Config, load_config
from .errors import EXIT_INVALID, EXIT_OK, EXIT_PARTIAL, ListenForgeError, LessonError
from .models import Lesson
from .parser import parse_lesson_file
from .paths import (
    ResolvedPaths,
    ensure_output_dir,
    iter_lesson_files,
    output_path_for,
    resolve_lesson_argument,
    resolve_paths,
    validate_input_dir,
)
from .pipeline import Outcome, RealPipeline, Result, run_one
from .tts.edge import EdgeTTS

app = typer.Typer(
    name="listenforge",
    help="Turn structured English listening lessons in Markdown into playable MP3 files.",
    add_completion=False,
    no_args_is_help=True,
)

console = Console()
err_console = Console(stderr=True)

InputOpt = Annotated[
    str | None,
    typer.Option("--input", metavar="PATH", help="Lesson directory. Default: ./input"),
]
OutputOpt = Annotated[
    str | None,
    typer.Option("--output", metavar="PATH", help="MP3 directory. Default: ./output"),
]
ConfigOpt = Annotated[
    Path | None,
    typer.Option(
        "--config", metavar="PATH", help="Config file. Default: ./config/listenforge.toml"
    ),
]
ForceOpt = Annotated[
    bool, typer.Option("--force", help="Regenerate output files that already exist.")
]
RefreshOpt = Annotated[
    bool,
    typer.Option(
        "--refresh-tts",
        help="Discard cached speech and re-synthesize. Separate from --force, which only "
        "concerns output files.",
    ),
]
DryRunOpt = Annotated[
    bool, typer.Option("--dry-run", help="Report what would happen; write nothing.")
]
JobsOpt = Annotated[
    int, typer.Option("--jobs", "-j", min=1, max=16, help="Lessons to process in parallel.")
]


@dataclass(slots=True)
class Context:
    config: Config
    paths: ResolvedPaths


def _setup(
    cli_input: str | None, cli_output: str | None, config_path: Path | None
) -> Context:
    config = load_config(config_path)
    paths = resolve_paths(
        cli_input,
        cli_output,
        config_input=config.paths.input,
        config_output=config.paths.output,
    )
    return Context(config=config, paths=paths)


def _fail(message: str, code: int = EXIT_INVALID) -> None:
    err_console.print(f"[red]{message}[/red]")
    raise typer.Exit(code)


def _build_pipeline(config: Config, *, refresh_tts: bool) -> tuple[RealPipeline, Cache]:
    ffmpeg = FFmpeg.discover(config.audio.ffmpeg, config.audio.ffprobe)
    ffmpeg.require_mp3_encoder()
    cache = Cache(enabled=config.tts.cache)
    if refresh_tts:
        removed = cache.clear_speech()
        console.print(f"[dim]Cleared {removed} cached speech segment(s).[/dim]")
    tts = EdgeTTS(concurrency=config.tts.concurrency)
    return RealPipeline(config=config, tts=tts, cache=cache, ffmpeg=ffmpeg), cache


# ---------------------------------------------------------------------------- generate


@app.command()
def generate(
    file: Annotated[str, typer.Argument(metavar="FILE", help="Lesson file name or path.")],
    input: InputOpt = None,
    output: OutputOpt = None,
    force: ForceOpt = False,
    refresh_tts: RefreshOpt = False,
    dry_run: DryRunOpt = False,
    config: ConfigOpt = None,
) -> None:
    """Generate one lesson.

    FILE may be a bare name resolved under INPUT ("001-job-interview.md", or just "001"),
    or an explicit path, which bypasses --input. The .md suffix is optional.
    """
    try:
        ctx = _setup(input, output, config)
        validate_input_dir(ctx.paths.input_dir, ctx.paths.input_display)
        lesson_file = resolve_lesson_argument(
            file, ctx.paths.input_dir, ctx.paths.input_display
        )
        lesson = parse_lesson_file(lesson_file)
        dest = output_path_for(lesson_file, ctx.paths.output_dir)

        if dry_run:
            _report_plan([(lesson_file, dest, lesson)], ctx, force=force)
            raise typer.Exit(EXIT_OK)

        ensure_output_dir(ctx.paths.output_dir, ctx.paths.output_display)
        pipeline, cache = _build_pipeline(ctx.config, refresh_tts=refresh_tts)
        result = asyncio.run(
            run_one(pipeline, cache, ctx.config, lesson, lesson_file, dest, force=force)
        )
    except ListenForgeError as exc:
        _fail(str(exc))
        return

    _print_result(result)
    if result.outcome is Outcome.FAILED:
        raise typer.Exit(EXIT_PARTIAL)


# ------------------------------------------------------------------------ generate-all


@app.command(name="generate-all")
def generate_all(
    input: InputOpt = None,
    output: OutputOpt = None,
    force: ForceOpt = False,
    refresh_tts: RefreshOpt = False,
    dry_run: DryRunOpt = False,
    jobs: JobsOpt = 2,
    config: ConfigOpt = None,
) -> None:
    """Generate every lesson in the input directory."""
    try:
        ctx = _setup(input, output, config)
        validate_input_dir(ctx.paths.input_dir, ctx.paths.input_display)
        lesson_files = iter_lesson_files(ctx.paths.input_dir)
        if not lesson_files:
            console.print(
                f"No lesson files (*.md) found in {ctx.paths.input_display}", style="yellow"
            )
            raise typer.Exit(EXIT_OK)

        parsed, parse_failures = _parse_all(lesson_files)
        _check_collisions(parsed, ctx.paths.output_dir)

        jobs_planned = [
            (path, output_path_for(path, ctx.paths.output_dir), lesson)
            for path, lesson in parsed
        ]
        if dry_run:
            _report_plan(jobs_planned, ctx, force=force)
            for failure in parse_failures:
                err_console.print(f"[red]{failure}[/red]\n")
            raise typer.Exit(EXIT_PARTIAL if parse_failures else EXIT_OK)

        ensure_output_dir(ctx.paths.output_dir, ctx.paths.output_display)
        pipeline, cache = _build_pipeline(ctx.config, refresh_tts=refresh_tts)
        results = asyncio.run(
            _run_batch(pipeline, cache, ctx.config, jobs_planned, jobs=jobs, force=force)
        )
    except ListenForgeError as exc:
        _fail(str(exc))
        return

    for result in results:
        _print_result(result)
    for failure in parse_failures:
        err_console.print(f"\n[red]{failure}[/red]")

    generated = sum(1 for r in results if r.outcome is Outcome.GENERATED)
    skipped = sum(1 for r in results if r.outcome is Outcome.SKIPPED)
    failed = sum(1 for r in results if r.outcome is Outcome.FAILED) + len(parse_failures)
    console.print(
        f"\n[bold]{generated} generated · {skipped} skipped · {failed} failed[/bold]"
    )
    if failed:
        raise typer.Exit(EXIT_PARTIAL)


async def _run_batch(
    pipeline,
    cache: Cache,
    config: Config,
    planned: list[tuple[Path, Path, Lesson]],
    *,
    jobs: int,
    force: bool,
) -> list[Result]:
    semaphore = asyncio.Semaphore(jobs)

    async def worker(lesson_file: Path, dest: Path, lesson: Lesson) -> Result:
        async with semaphore:
            return await run_one(
                pipeline, cache, config, lesson, lesson_file, dest, force=force
            )

    results = await asyncio.gather(
        *(worker(f, d, lesson) for f, d, lesson in planned)
    )
    cache.flush()
    return list(results)


# -------------------------------------------------------------------------------- list


@app.command(name="list")
def list_command(
    input: InputOpt = None,
    output: OutputOpt = None,
    json: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
    config: ConfigOpt = None,
) -> None:
    """List lessons and whether their MP3 has been generated."""
    try:
        ctx = _setup(input, output, config)
        validate_input_dir(ctx.paths.input_dir, ctx.paths.input_display)
        lesson_files = iter_lesson_files(ctx.paths.input_dir)
        parsed, parse_failures = _parse_all(lesson_files)
    except ListenForgeError as exc:
        _fail(str(exc))
        return

    cache = Cache(enabled=ctx.config.tts.cache)
    fingerprint = ctx.config.fingerprint()
    rows = []
    for lesson_file, lesson in parsed:
        dest = output_path_for(lesson_file, ctx.paths.output_dir)
        if not dest.exists():
            status, stale = "NOT GENERATED", False
        else:
            stale = cache.is_stale(dest, lesson.content_hash(), fingerprint)
            status = "GENERATED"
        rows.append(
            {
                "id": lesson.meta.id,
                "title": lesson.meta.title,
                "level": lesson.meta.level,
                "status": status,
                "stale": stale,
                "input": str(lesson_file),
                "output": str(dest),
            }
        )

    if json:
        console.print_json(jsonlib.dumps({"lessons": rows, "errors": [str(e) for e in parse_failures]}))
        raise typer.Exit(EXIT_PARTIAL if parse_failures else EXIT_OK)

    table = Table(box=None, pad_edge=False)
    table.add_column("ID")
    table.add_column("TITLE")
    table.add_column("LEVEL")
    table.add_column("STATUS")
    for row in rows:
        status = row["status"] + (" (stale)" if row["stale"] else "")
        colour = "yellow" if row["stale"] else ("green" if row["status"] == "GENERATED" else "dim")
        table.add_row(row["id"], row["title"], row["level"], f"[{colour}]{status}[/{colour}]")
    console.print(table)

    for failure in parse_failures:
        err_console.print(f"\n[red]{failure}[/red]")
    if parse_failures:
        raise typer.Exit(EXIT_PARTIAL)


# ------------------------------------------------------------------------------ doctor


@app.command()
def doctor(config: ConfigOpt = None) -> None:
    """Check that the audio toolchain and the speech endpoint are usable."""
    cfg = load_config(config)
    ok = True

    try:
        ffmpeg = FFmpeg.discover(cfg.audio.ffmpeg, cfg.audio.ffprobe)
        console.print(f"[green]ok[/green]   ffmpeg: {ffmpeg.ffmpeg}")
        console.print(f"[dim]     {ffmpeg.version()}[/dim]")
        if ffmpeg.has_mp3_encoder():
            console.print("[green]ok[/green]   libmp3lame encoder present")
        else:
            console.print("[red]FAIL[/red] libmp3lame encoder missing — cannot write MP3")
            ok = False
        if ffmpeg.ffprobe:
            console.print(f"[green]ok[/green]   ffprobe: {ffmpeg.ffprobe}")
        else:
            console.print("[yellow]warn[/yellow] ffprobe not found — duration checks disabled")
    except ListenForgeError as exc:
        console.print(f"[red]FAIL[/red] {exc}")
        ok = False

    cache = Cache(enabled=cfg.tts.cache)
    console.print(f"[green]ok[/green]   cache: {cache.root}")

    try:
        voices = asyncio.run(_probe_voices())
        console.print(f"[green]ok[/green]   speech endpoint reachable ({voices} voices)")
    except Exception as exc:  # noqa: BLE001 - doctor reports, never raises
        console.print(f"[red]FAIL[/red] speech endpoint unreachable: {exc}")
        console.print(
            "[dim]     Its token is derived from the system clock; a wrong date/time "
            "causes persistent 403s.[/dim]"
        )
        ok = False

    for voice in (cfg.voices.vietnamese, *cfg.voices.english):
        console.print(f"[dim]     voice configured: {voice}[/dim]")

    if not ok:
        raise typer.Exit(EXIT_INVALID)


async def _probe_voices() -> int:
    from .tts.edge import list_voices

    return len(await list_voices())


# -------------------------------------------------------------------------------- init


@app.command()
def init(
    input: InputOpt = None,
    output: OutputOpt = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing files.")] = False,
) -> None:
    """Create the default directories, a config file and sample lessons."""
    ctx = _setup(input, output, None)
    try:
        ctx.paths.input_dir.mkdir(parents=True, exist_ok=True)
        ensure_output_dir(ctx.paths.output_dir, ctx.paths.output_display)
    except ListenForgeError as exc:
        _fail(str(exc))
        return

    written = samples.write_samples(ctx.paths.input_dir, force=force)
    for path in written:
        console.print(f"  created {path.name}")

    config_file = Path.cwd() / "config" / "listenforge.toml"
    if force or not config_file.exists():
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(samples.DEFAULT_CONFIG, encoding="utf-8")
        console.print("  created config/listenforge.toml")

    console.print(
        f"\n[green]Ready.[/green] input={ctx.paths.input_display} "
        f"output={ctx.paths.output_display}\nNext: listenforge list"
    )


# ----------------------------------------------------------------------------- helpers


def _parse_all(lesson_files: list[Path]) -> tuple[list[tuple[Path, Lesson]], list[LessonError]]:
    parsed: list[tuple[Path, Lesson]] = []
    failures: list[LessonError] = []
    for path in lesson_files:
        try:
            parsed.append((path, parse_lesson_file(path)))
        except LessonError as exc:
            failures.append(exc)
    return parsed, failures


def _check_collisions(parsed: list[tuple[Path, Lesson]], output_dir: Path) -> None:
    """Duplicate lesson ids (§14.12) and output names that would overwrite each other.

    The name check is case-insensitive because APFS and FAT are: `001.md` and `001.MD`
    resolve to the same MP3.
    """
    by_id: dict[str, Path] = {}
    for path, lesson in parsed:
        previous = by_id.get(lesson.meta.id)
        if previous is not None:
            raise ListenForgeError(
                f"Error: Duplicate lesson id {lesson.meta.id!r} in:\n"
                f"  {previous}\n  {path}"
            )
        by_id[lesson.meta.id] = path

    by_name: dict[str, Path] = {}
    for path, _ in parsed:
        name = output_path_for(path, output_dir).name.lower()
        previous = by_name.get(name)
        if previous is not None:
            raise ListenForgeError(
                f"Error: These lessons would write to the same output file {name!r}:\n"
                f"  {previous}\n  {path}"
            )
        by_name[name] = path


def _report_plan(
    planned: list[tuple[Path, Path, Lesson]], ctx: Context, *, force: bool
) -> None:
    console.print(f"input  = {ctx.paths.input_display}  [dim]{ctx.paths.input_dir}[/dim]")
    console.print(f"output = {ctx.paths.output_display}  [dim]{ctx.paths.output_dir}[/dim]\n")
    cache = Cache(enabled=ctx.config.tts.cache)
    fingerprint = ctx.config.fingerprint()
    for lesson_file, dest, lesson in planned:
        if dest.exists() and not force:
            stale = cache.is_stale(dest, lesson.content_hash(), fingerprint)
            action = "REGENERATE (stale)" if stale else "SKIP (exists)"
        else:
            action = "GENERATE"
        console.print(f"  {action:20} {lesson_file.name} -> {dest.name}")


def _print_result(result: Result) -> None:
    if result.outcome is Outcome.GENERATED:
        console.print(f"[green]generated[/green] {result.output_file}")
    elif result.outcome is Outcome.SKIPPED:
        console.print(
            f"[dim]skipped[/dim]   {result.output_file} — {result.detail} "
            f"[dim](use --force to regenerate)[/dim]"
        )
    else:
        err_console.print(f"[red]failed[/red]    {result.lesson_file}\n{result.detail}")


def main() -> None:  # pragma: no cover - console-script shim
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
