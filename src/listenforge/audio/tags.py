"""ID3 tagging aimed at cheap hardware MP3 players."""

from __future__ import annotations

from pathlib import Path

from ..models import LessonMeta


def write_tags(path: Path, meta: LessonMeta) -> None:
    """Write ID3v2.3 *and* ID3v1.

    v2.3 rather than v2.4 because many basic players render v2.4/UTF-8 as mojibake, and
    lesson titles are frequently Vietnamese. The v1 tag is the last-resort fallback for
    the cheapest firmware. Note most such players sort by *filename*, not tags — the
    numeric prefix in the lesson filename is what actually controls play order.
    """
    from mutagen.id3 import ID3, TALB, TCON, TIT2, TPE1, TRCK, ID3NoHeaderError

    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()

    tags.delall("TIT2")
    tags.delall("TPE1")
    tags.delall("TALB")
    tags.delall("TRCK")
    tags.delall("TCON")

    tags.add(TIT2(encoding=1, text=[f"{meta.id} {meta.title}".strip()]))
    tags.add(TPE1(encoding=1, text=["ListenForge"]))
    tags.add(TALB(encoding=1, text=[f"{meta.topic} ({meta.level})"]))
    tags.add(TCON(encoding=1, text=["Speech"]))
    if meta.id.isdigit():
        tags.add(TRCK(encoding=0, text=[str(int(meta.id))]))

    tags.save(path, v2_version=3, v1=2)
