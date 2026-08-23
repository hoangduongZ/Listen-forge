"""End-to-end CLI behaviour.

The pipeline is swapped for the stub, so path precedence, --force, skip logic and exit
codes are all covered without touching the network or ffmpeg.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from listenforge import cli
from listenforge.cache import Cache
from listenforge.errors import EXIT_INVALID, EXIT_OK, EXIT_PARTIAL
from listenforge.pipeline import StubPipeline

runner = CliRunner()


@pytest.fixture
def stub(monkeypatch, tmp_path):
    """Replace the real pipeline; keep a per-test cache so the manifest is isolated."""
    pipeline = StubPipeline()
    cache = Cache(root=tmp_path / "cache")

    def build(config, *, refresh_tts):
        return pipeline, cache

    monkeypatch.setattr(cli, "_build_pipeline", build)
    monkeypatch.setattr(cli, "Cache", lambda **_kwargs: cache)
    return pipeline


@pytest.fixture(autouse=True)
def isolated_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)


def invoke(*args):
    return runner.invoke(cli.app, list(args))


def test_help_documents_the_shared_options():
    for command in ("generate", "generate-all", "list"):
        result = invoke(command, "--help")
        assert result.exit_code == EXIT_OK
        assert "--input" in result.output
        assert "--output" in result.output
    assert "--force" in invoke("generate", "--help").output
    assert "--force" in invoke("generate-all", "--help").output


def test_generate_uses_default_paths(stub, lesson_dir, tmp_path):
    # Default input is ./input relative to cwd.
    (tmp_path / "input").mkdir(exist_ok=True)
    for source in lesson_dir.iterdir():
        (tmp_path / "input" / source.name).write_text(source.read_text(encoding="utf-8"))

    result = invoke("generate", "001-java-backend-interview.md")

    assert result.exit_code == EXIT_OK
    assert (tmp_path / "output" / "001-java-backend-interview.mp3").is_file()


def test_generate_honours_custom_paths(stub, lesson_dir, tmp_path):
    result = invoke(
        "generate",
        "001-java-backend-interview.md",
        "--input", str(lesson_dir),
        "--output", str(tmp_path / "audio"),
    )

    assert result.exit_code == EXIT_OK
    assert (tmp_path / "audio" / "001-java-backend-interview.mp3").is_file()


def test_generate_all_creates_one_mp3_per_lesson(stub, lesson_dir, tmp_path):
    out = tmp_path / "mp3"
    result = invoke("generate-all", "--input", str(lesson_dir), "--output", str(out))

    assert result.exit_code == EXIT_OK
    assert sorted(p.name for p in out.glob("*.mp3")) == [
        "001-java-backend-interview.mp3",
        "002-toeic-part3-office-renovation.mp3",
        "003-daily-conversation-dinner.mp3",
    ]


def test_existing_output_is_skipped_then_regenerated_with_force(stub, lesson_dir, tmp_path):
    out = tmp_path / "mp3"
    args = ("generate-all", "--input", str(lesson_dir), "--output", str(out))

    assert invoke(*args).exit_code == EXIT_OK
    assert len(stub.generated) == 3

    second = invoke(*args)
    assert "skipped" in second.output
    assert len(stub.generated) == 3, "nothing should have been rewritten"

    forced = invoke(*args, "--force")
    assert forced.exit_code == EXIT_OK
    assert len(stub.generated) == 6


def test_editing_a_lesson_marks_it_stale_and_rebuilds_without_force(
    stub, lesson_dir, tmp_path
):
    out = tmp_path / "mp3"
    args = ("generate-all", "--input", str(lesson_dir), "--output", str(out))
    invoke(*args)
    assert len(stub.generated) == 3

    target = lesson_dir / "003-daily-conversation-dinner.md"
    target.write_text(
        target.read_text(encoding="utf-8").replace("I'm really hungry", "I'm starving"),
        encoding="utf-8",
    )

    listing = invoke("list", "--input", str(lesson_dir), "--output", str(out))
    assert "stale" in listing.output

    invoke(*args)
    assert len(stub.generated) == 4


def test_dry_run_writes_nothing(stub, lesson_dir, tmp_path):
    out = tmp_path / "mp3"
    result = invoke("generate-all", "--input", str(lesson_dir), "--output", str(out), "--dry-run")

    assert result.exit_code == EXIT_OK
    assert "GENERATE" in result.output
    assert not out.exists()
    assert stub.generated == []


def test_list_reports_status_per_lesson(stub, lesson_dir, tmp_path):
    out = tmp_path / "mp3"
    invoke("generate", "001-java-backend-interview.md", "--input", str(lesson_dir),
           "--output", str(out))

    result = invoke("list", "--input", str(lesson_dir), "--output", str(out))

    assert result.exit_code == EXIT_OK
    assert "GENERATED" in result.output
    assert "NOT GENERATED" in result.output
    for header in ("ID", "TITLE", "LEVEL", "STATUS"):
        assert header in result.output


def test_list_json_is_machine_readable(stub, lesson_dir, tmp_path):
    import json

    result = invoke("list", "--input", str(lesson_dir), "--output", str(tmp_path / "mp3"),
                    "--json")
    payload = json.loads(result.output)

    assert [row["id"] for row in payload["lessons"]] == ["001", "002", "003"]
    assert all(row["status"] == "NOT GENERATED" for row in payload["lessons"])


def test_missing_input_directory_exits_two(stub, tmp_path):
    result = invoke("generate-all", "--input", str(tmp_path / "nope"))

    assert result.exit_code == EXIT_INVALID
    assert "Error: Input directory does not exist:" in result.output


def test_missing_lesson_file_exits_two(stub, lesson_dir):
    result = invoke("generate", "999.md", "--input", str(lesson_dir))

    assert result.exit_code == EXIT_INVALID
    assert "Error: Input file does not exist:" in result.output


def test_unparseable_lesson_is_reported_and_batch_exits_one(stub, lesson_dir, tmp_path):
    (lesson_dir / "004-broken.md").write_text("no front matter here\n", encoding="utf-8")

    result = invoke("generate-all", "--input", str(lesson_dir), "--output", str(tmp_path / "mp3"))

    assert result.exit_code == EXIT_PARTIAL
    assert "004-broken.md" in result.output
    # The three valid lessons still get built.
    assert len(stub.generated) == 3


def test_duplicate_lesson_ids_are_rejected(stub, lesson_dir, tmp_path):
    source = (lesson_dir / "001-java-backend-interview.md").read_text(encoding="utf-8")
    (lesson_dir / "004-copy.md").write_text(source, encoding="utf-8")

    result = invoke("generate-all", "--input", str(lesson_dir), "--output", str(tmp_path / "mp3"))

    assert result.exit_code == EXIT_INVALID
    assert "Duplicate lesson id" in result.output


def test_init_scaffolds_a_working_project(tmp_path):
    result = invoke("init")

    assert result.exit_code == EXIT_OK
    assert (tmp_path / "input" / "001-java-backend-interview.md").is_file()
    assert (tmp_path / "config" / "listenforge.toml").is_file()
    assert (tmp_path / "output").is_dir()
