from __future__ import annotations

from dataclasses import replace

import pytest

from listenforge.config import Config, Voices, load_config
from listenforge.errors import ListenForgeError

SAMPLE = """
[paths]
input  = "./lessons"
output = "./mp3"

[pauses]
after_context = 1.0
between_lines = 0.25

[speed]
slow = "-45%"

[repeat]
normal_times = 3

[voices]
vietnamese = "vi-VN-NamMinhNeural"
english = ["en-GB-SoniaNeural"]
multi_speaker = false

[audio]
bitrate = "64k"
"""


def test_defaults_match_the_documented_sequence():
    config = Config()
    assert config.repeat_normal_times == 2  # two normal passes, then the slow one
    assert config.speed.normal == "+0%"
    assert config.speed.slow.startswith("-")
    assert config.audio.sample_rate == 24000


def test_loads_from_config_subdirectory(tmp_path):
    target = tmp_path / "config" / "listenforge.toml"
    target.parent.mkdir()
    target.write_text(SAMPLE, encoding="utf-8")

    config = load_config(cwd=tmp_path)

    assert config.paths.input == "./lessons"
    assert config.pauses.after_context == 1.0
    assert config.pauses.between_lines == 0.25
    assert config.speed.slow == "-45%"
    assert config.repeat_normal_times == 3
    assert config.voices.english == ("en-GB-SoniaNeural",)
    assert config.voices.multi_speaker is False
    assert config.audio.bitrate == "64k"


def test_config_subdirectory_wins_over_root_file(tmp_path):
    (tmp_path / "listenforge.toml").write_text('[paths]\ninput = "./root"\n', encoding="utf-8")
    nested = tmp_path / "config"
    nested.mkdir()
    (nested / "listenforge.toml").write_text('[paths]\ninput = "./nested"\n', encoding="utf-8")

    assert load_config(cwd=tmp_path).paths.input == "./nested"


def test_unset_values_keep_their_defaults(tmp_path):
    target = tmp_path / "listenforge.toml"
    target.write_text('[pauses]\nafter_context = 5.0\n', encoding="utf-8")

    config = load_config(cwd=tmp_path)

    assert config.pauses.after_context == 5.0
    assert config.pauses.after_english == 2.5  # untouched default


def test_explicit_missing_config_is_an_error(tmp_path):
    with pytest.raises(ListenForgeError) as excinfo:
        load_config(tmp_path / "absent.toml")
    assert "Config file does not exist" in str(excinfo.value)


def test_env_overrides_the_file(tmp_path, monkeypatch):
    (tmp_path / "listenforge.toml").write_text('[paths]\ninput = "./from-file"\n', encoding="utf-8")
    monkeypatch.setenv("LISTENFORGE_INPUT", "./from-env")

    assert load_config(cwd=tmp_path).paths.input == "./from-env"


def test_fingerprint_tracks_audio_settings_only():
    base = Config()

    # Moving the output directory must not invalidate already-generated audio.
    moved = replace(base, paths=replace(base.paths, output="/somewhere/else"))
    assert moved.fingerprint() == base.fingerprint()

    # Changing a voice must.
    revoiced = replace(base, voices=Voices(english=("en-AU-NatashaNeural",)))
    assert revoiced.fingerprint() != base.fingerprint()

    # So must a pause length.
    repaused = replace(base, pauses=replace(base.pauses, after_english=9.0))
    assert repaused.fingerprint() != base.fingerprint()
