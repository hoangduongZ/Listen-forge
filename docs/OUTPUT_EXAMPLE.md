# Output Example

## Naming

One valid lesson produces exactly one MP3, named after the input file:

```text
input/001-java-backend-interview.md  ->  output/001-java-backend-interview.mp3
```

The numeric prefix is kept on purpose: most cheap MP3 players sort by **filename**, not by
ID3 tags, so the prefix is what actually controls play order.

## Audio sequence

Each file plays in this order:

```text
Vietnamese context
      ↓  pause  (after_context, default 2.0s)
English — normal speed
      ↓  pause  (after_english, default 2.5s)
English — normal speed again
      ↓  pause  (after_english, default 2.5s)
English — slow speed  (default -30%)
```

Between dialogue turns there is a shorter gap (`between_lines`, default 0.6s).

The slow pass is re-synthesized at a slower speaking rate by the voice itself, not
time-stretched from the normal pass — so it stays natural instead of sounding dragged.

Every duration and speed is configurable in `config/listenforge.toml`. The normal-speed
block is synthesized once and reused for the repeat.

## Real output from the shipped samples

```text
001-java-backend-interview.mp3          224s   1314 KB
002-toeic-part3-office-renovation.mp3   188s   1103 KB
003-daily-conversation-dinner.mp3       185s   1085 KB
```

## File properties

```text
codec        mp3 (MPEG audio layer 3)
sample rate  24000 Hz
channels     1 (mono)
bit rate     48 kbps, constant
```

Mono 24 kHz / 48 kbps CBR is chosen to match what the speech backend produces natively.
Because every part shares these parameters, assembly is a stream copy rather than a
re-encode: faster, and with no generational quality loss. Constant bitrate also means
players that compute duration from file size get it right.

## ID3 tags

```text
title   001 Java Backend Interview
artist  ListenForge
album   career (B1)
track   1
genre   Speech
```

Written as ID3v2.3 **and** ID3v1. v2.3 rather than v2.4 because many basic players render
v2.4/UTF-8 as mojibake, and lesson titles are often Vietnamese; the v1 tag covers the
cheapest firmware that ignores v2 entirely.

## Writing straight to a memory card

```bash
listenforge generate-all --input ./input --output /Volumes/SDCARD/English
```

Files are published atomically — written to a temporary name beside the destination, then
moved into place — so an interrupted run never leaves a half-written MP3 on the card. The
temporary file is created *next to the destination* rather than in the cache directory,
because moving a file across filesystems fails.

The output directory is probed for writability before any synthesis starts, so a
read-only or full card fails immediately instead of after minutes of work.

## Regeneration

```bash
listenforge generate-all           # existing files are skipped
listenforge generate-all --force   # rebuild everything
```

Editing a lesson marks its MP3 stale, and the next run rebuilds it without `--force`:

```text
ID   TITLE                   LEVEL  STATUS
001  Java Backend Interview  B1     GENERATED
002  Office Renovation       B2     GENERATED
003  Dinner Plans            A2     GENERATED (stale)
```

`--force` only concerns output files. Cached speech survives it, so a rebuild costs no
network time. Use `--refresh-tts` to discard the speech cache as well.
