# ListenForge

Turn structured Markdown listening lessons into MP3 files you can drop onto a cheap MP3
player or a microSD card.

```text
input/001-java-backend-interview.md  ->  output/001-java-backend-interview.mp3
```

Each lesson becomes one file: Vietnamese context, a pause, the English passage at normal
speed, again at normal speed, then once slowly.

## Requirements

- Python 3.11+ (managed by [uv](https://docs.astral.sh/uv/))
- `ffmpeg` with the `libmp3lame` encoder — `brew install ffmpeg`
- An internet connection for speech synthesis (results are cached)

## Setup

```bash
uv sync
uv run listenforge doctor     # verify ffmpeg, libmp3lame and the speech endpoint
uv run listenforge init       # create input/, output/, config/ and three sample lessons
```

## Usage

```bash
listenforge generate 001-java-backend-interview.md   # one lesson
listenforge generate 001                             # unique prefix also works
listenforge generate-all                             # everything in ./input
listenforge list                                     # what exists, what does not
```

Custom locations, including other volumes:

```bash
listenforge generate-all --input ./lessons --output ./audio
listenforge generate-all --input ./lessons --output /Volumes/SDCARD/English
```

Paths resolve the same way for every command:

```text
INPUT  = --input  if given, else config, else ./input
OUTPUT = --output if given, else config, else ./output
```

### Commands

| Command | Purpose |
|---|---|
| `generate FILE` | Build one lesson. |
| `generate-all` | Build every `*.md` in the input directory. |
| `list` | Show id, title, level and generation status. `--json` for scripting. |
| `doctor` | Check the audio toolchain and the speech endpoint. |
| `init` | Scaffold directories, config and sample lessons. |

### Options

| Option | Applies to | Meaning |
|---|---|---|
| `--input PATH` | all | Lesson directory. Default `./input`. |
| `--output PATH` | all | MP3 directory. Default `./output`. |
| `--force` | generate, generate-all | Rebuild output files that already exist. |
| `--refresh-tts` | generate, generate-all | Also discard cached speech and re-synthesize. |
| `--dry-run` | generate, generate-all | Report the plan; write nothing. |
| `--jobs N` | generate-all | Lessons in parallel. Default 2. |
| `--config PATH` | all | Config file. Default `./config/listenforge.toml`. |

`--force` and `--refresh-tts` are deliberately separate. `--force` rebuilds MP3s from
cached speech, which is free; `--refresh-tts` re-downloads the speech, which is not.

## Layout

```text
├── input/                  lesson Markdown
├── output/                 generated MP3s
├── config/listenforge.toml voices, pauses, speeds
├── docs/
│   ├── INPUT_FORMAT.md     the lesson format contract
│   ├── OUTPUT_EXAMPLE.md   what the MP3s look like
│   └── IMPLEMENTATION-PLAN.md
└── src/listenforge/
```

## Configuration

`config/listenforge.toml` controls how the audio is rendered. Lesson files never carry
voice or timing settings — that separation is what lets you retune every lesson at once.

```toml
[pauses]
after_context = 2.0
after_english = 2.5
between_lines = 0.6

[speed]
normal = "+0%"
slow   = "-30%"

[voices]
vietnamese    = "vi-VN-HoaiMyNeural"
english       = ["en-US-GuyNeural", "en-US-AriaNeural"]
multi_speaker = true
```

With `multi_speaker`, dialogue speakers get different voices, assigned in first-appearance
order so runs are reproducible.

## How it works

```text
Markdown -> parser -> validated Lesson -> TTS -> assembly -> MP3
```

The speech backend emits 24 kHz mono 48 kbps MP3, and generated silence is rendered to
match. Because every part shares those parameters, the final file is assembled by stream
copy instead of re-encoding — fast, and lossless across the joins.

Three cache tiers live under the user cache directory (`listenforge doctor` prints the
path): one entry per utterance, one per assembled block, one manifest recording what each
output was built from. The normal-speed block is synthesized once and used twice. Editing a
lesson changes its content hash, which is how staleness is detected without `--force`.

## Development

```bash
uv run pytest
```

Tests use an offline speech provider, so the suite needs no network. `ffmpeg`-dependent
tests skip automatically when it is absent.

## Notes

- Lesson files must use `schema_version: "1.0"` and the `## Context` / `## Listening`
  headings. The older `[CONTEXT_VI]` / `[ENGLISH]` bracket dialect is rejected with a
  message explaining the conversion — see [docs/INPUT_FORMAT.md](docs/INPUT_FORMAT.md).
- Speech synthesis authenticates with a token derived from the system clock. A wrong
  system date causes persistent `403` errors; `doctor` says so when it happens.
