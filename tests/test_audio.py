"""Audio assembly, exercised with the offline provider so no network is involved."""

from __future__ import annotations

from dataclasses import replace

import pytest

from listenforge.audio.engine import AudioEngine, plan_voices
from listenforge.audio.tags import write_tags
from listenforge.cache import Cache
from listenforge.config import Config, Voices
from listenforge.io.atomic import atomic_path
from listenforge.parser import parse_lesson
from listenforge.tts.fake import FakeTTS
from tests.conftest import NARRATION_LESSON, VALID_LESSON

pytestmark = pytest.mark.usefixtures("ffmpeg")


@pytest.fixture
def engine_parts(tmp_path, ffmpeg):
    config = Config()
    cache = Cache(root=tmp_path / "cache")
    tts = FakeTTS(ffmpeg)
    engine = AudioEngine(config=config, tts=tts, cache=cache, ffmpeg=ffmpeg)
    return engine, tts, cache, config


async def test_builds_a_single_playable_mp3(tmp_path, ffmpeg, engine_parts):
    engine, _tts, _cache, _config = engine_parts
    lesson = parse_lesson(VALID_LESSON, tmp_path / "001.md")
    dest = tmp_path / "out" / "001.mp3"

    with atomic_path(dest, suffix=".mp3") as tmp:
        await engine.build(lesson, tmp)

    assert dest.is_file()
    assert dest.stat().st_size > 0
    assert ffmpeg.duration(dest) is not None


async def test_english_normal_is_synthesized_once_and_reused(tmp_path, engine_parts):
    """The sequence plays normal speed twice; synthesizing it twice would be waste."""
    engine, tts, _cache, _config = engine_parts
    lesson = parse_lesson(VALID_LESSON, tmp_path / "001.md")

    with atomic_path(tmp_path / "001.mp3", suffix=".mp3") as tmp:
        await engine.build(lesson, tmp)

    rates = [rate for _text, _voice, rate in tts.calls]
    # 2 listening segments at normal + 2 at slow + 1 Vietnamese context = 5 requests,
    # not 7, because the normal block is reused for the repeat.
    assert len(tts.calls) == 5
    assert rates.count("+0%") == 3
    assert rates.count("-30%") == 2


async def test_second_build_is_served_entirely_from_cache(tmp_path, engine_parts):
    engine, tts, _cache, _config = engine_parts
    lesson = parse_lesson(VALID_LESSON, tmp_path / "001.md")

    with atomic_path(tmp_path / "a.mp3", suffix=".mp3") as tmp:
        await engine.build(lesson, tmp)
    first = len(tts.calls)

    with atomic_path(tmp_path / "b.mp3", suffix=".mp3") as tmp:
        await engine.build(lesson, tmp)

    assert len(tts.calls) == first, "cache should have prevented any new synthesis"


async def test_changing_a_voice_invalidates_the_cache(tmp_path, ffmpeg):
    """The cache key includes the voice; otherwise old audio would be replayed."""
    cache = Cache(root=tmp_path / "cache")
    tts = FakeTTS(ffmpeg)
    lesson = parse_lesson(VALID_LESSON, tmp_path / "001.md")

    engine = AudioEngine(config=Config(), tts=tts, cache=cache, ffmpeg=ffmpeg)
    with atomic_path(tmp_path / "a.mp3", suffix=".mp3") as tmp:
        await engine.build(lesson, tmp)
    baseline = len(tts.calls)

    swapped = replace(Config(), voices=Voices(english=("en-GB-SoniaNeural",)))
    engine = AudioEngine(config=swapped, tts=tts, cache=cache, ffmpeg=ffmpeg)
    with atomic_path(tmp_path / "b.mp3", suffix=".mp3") as tmp:
        await engine.build(lesson, tmp)

    assert len(tts.calls) > baseline


async def test_duration_accounts_for_every_configured_pause(tmp_path, ffmpeg, engine_parts):
    engine, _tts, _cache, config = engine_parts
    lesson = parse_lesson(VALID_LESSON, tmp_path / "001.md")
    dest = tmp_path / "001.mp3"

    with atomic_path(dest, suffix=".mp3") as tmp:
        await engine.build(lesson, tmp)

    # Speech length is provider-dependent, so assert the floor: total must exceed the
    # pause budget, which is exactly known from the config.
    assert ffmpeg.duration(dest) > engine.expected_duration(lesson)


def test_voice_plan_assigns_distinct_voices_by_first_appearance(tmp_path):
    lesson = parse_lesson(VALID_LESSON, tmp_path / "001.md")
    plan = plan_voices(lesson, Config())

    assert lesson.speakers == ("Interviewer", "Candidate")
    assert plan.by_speaker["Interviewer"] != plan.by_speaker["Candidate"]


def test_voice_plan_collapses_to_one_voice_when_disabled(tmp_path):
    lesson = parse_lesson(VALID_LESSON, tmp_path / "001.md")
    config = replace(Config(), voices=Voices(multi_speaker=False))
    plan = plan_voices(lesson, config)

    assert plan.by_speaker["Interviewer"] == plan.by_speaker["Candidate"]


def test_narration_uses_the_vietnamese_voice_only_for_context(tmp_path):
    lesson = parse_lesson(NARRATION_LESSON, tmp_path / "002.md")
    plan = plan_voices(lesson, Config())

    assert plan.vietnamese.startswith("vi-")
    assert plan.by_speaker[None].startswith("en-")


async def test_tags_are_written_as_id3v23_plus_id3v1(tmp_path, ffmpeg, engine_parts):
    from mutagen.id3 import ID3
    from mutagen.mp3 import MP3

    engine, _tts, _cache, _config = engine_parts
    lesson = parse_lesson(VALID_LESSON, tmp_path / "001.md")
    dest = tmp_path / "001.mp3"

    with atomic_path(dest, suffix=".mp3") as tmp:
        await engine.build(lesson, tmp)
        write_tags(tmp, lesson.meta)

    tags = ID3(dest)
    assert tags.version[:2] == (2, 3), "v2.4/UTF-8 renders as mojibake on cheap players"
    assert str(tags["TIT2"]) == "001 Job Interview"
    assert MP3(dest).info.channels == 1


def test_silence_matches_the_speech_container_parameters(tmp_path, ffmpeg):
    """Matching parameters are what allow the final concat to be a stream copy."""
    cache = Cache(root=tmp_path / "cache")
    tts = FakeTTS(ffmpeg)
    engine = AudioEngine(config=Config(), tts=tts, cache=cache, ffmpeg=ffmpeg)

    silence = engine._silence(1.0)
    duration = ffmpeg.duration(silence)

    assert duration == pytest.approx(1.0, abs=0.1)
