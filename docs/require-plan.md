# ListenForge — CLI Input / Output Specification

Build a local CLI tool called **ListenForge**.

The tool converts structured English listening lesson files into playable MP3 audio files.

The implementation language, architecture, libraries, TTS provider, audio processing technology, and implementation plan are entirely up to you.

This specification defines the required **CLI behavior, input, output, and path handling**.

---

# 1. Default Directory Structure

The default project structure is:

```text
listenforge/
├── input/
├── output/
└── ...
```

Default input directory:

```text
./input
```

Default output directory:

```text
./output
```

If the user does not specify custom paths, the tool must use these defaults.

---

# 2. Custom Input / Output Paths

The CLI MUST support custom input and output locations.

Use:

```bash
--input <PATH>
--output <PATH>
```

Examples:

```bash
listenforge generate 001.md --input ./input --output ./output
```

```bash
listenforge generate-all --input ./lessons --output ./mp3
```

Absolute paths must also be supported:

```bash
listenforge generate-all \
  --input /home/user/english-lessons \
  --output /media/sdcard/english
```

The paths may point to different directories and different storage devices.

---

# 3. Path Precedence

The behavior must be:

```text
CLI --input / --output
        ↓
Use explicitly provided paths
        ↓
Otherwise
        ↓
Use default paths
```

Therefore:

```bash
listenforge generate-all
```

means:

```text
input  = ./input
output = ./output
```

while:

```bash
listenforge generate-all --input ./lessons
```

means:

```text
input  = ./lessons
output = ./output
```

and:

```bash
listenforge generate-all --output ./mp3
```

means:

```text
input  = ./input
output = ./mp3
```

and:

```bash
listenforge generate-all \
  --input ./lessons \
  --output ./mp3
```

means:

```text
input  = ./lessons
output = ./mp3
```

---

# 4. Generate One Lesson

The CLI must support generating one specific lesson.

Example:

```bash
listenforge generate 001-job-interview.md
```

Default behavior:

```text
Input:
./input/001-job-interview.md

Output:
./output/001-job-interview.mp3
```

Custom paths:

```bash
listenforge generate 001-job-interview.md \
  --input ./lessons \
  --output ./generated-audio
```

Result:

```text
./generated-audio/001-job-interview.mp3
```

---

# 5. Generate-All

The CLI must support batch generation.

Example:

```bash
listenforge generate-all
```

Equivalent to:

```text
Input:
./input/

Output:
./output/
```

Custom:

```bash
listenforge generate-all \
  --input ./lessons \
  --output ./generated-audio
```

The tool must scan the specified input directory and process all supported lesson files.

Example:

```text
lessons/
├── 001-job-interview.md
├── 002-daily-meeting.md
├── 003-database-problem.md
└── 004-code-review.md
```

Result:

```text
generated-audio/
├── 001-job-interview.mp3
├── 002-daily-meeting.mp3
├── 003-database-problem.mp3
└── 004-code-review.mp3
```

---

# 6. Input File

The primary lesson format is Markdown.

Example:

```markdown
---
id: 001
title: Job Interview
level: B1
topic: Career
---

[CONTEXT_VI]

Bạn đang tham gia một buổi phỏng vấn xin việc cho vị trí Java Developer.
Nhà tuyển dụng hỏi về kinh nghiệm làm việc và một dự án gần đây của bạn.

[ENGLISH]

Interviewer: So, could you tell me a little bit about your experience with Java?

Candidate: Sure. I've been working with Java for about two years.
Most recently, I worked on a Spring Boot application for managing interviews.

[VOCABULARY]

a little bit about = một chút về
most recently = gần đây nhất
be responsible for = chịu trách nhiệm về
```

Required sections:

```text
[CONTEXT_VI]
[ENGLISH]
```

Optional section:

```text
[VOCABULARY]
```

---

# 7. Output

One valid lesson must produce exactly one main MP3 file.

Example:

```text
001-job-interview.md
        ↓
001-job-interview.mp3
```

The filename should be derived from the input filename unless there is a strong technical reason to use another deterministic naming strategy.

---

# 8. Generated Audio Sequence

The final MP3 should contain:

```text
Vietnamese Context
        ↓
Pause
        ↓
English — Normal Speed
        ↓
Pause
        ↓
English — Normal Speed Again
        ↓
Pause
        ↓
English — Slow Speed
```

The exact pause durations and playback speeds should be configurable.

The final result must be a single normal MP3 file suitable for playback on a basic MP3 player.

---

# 9. Force Regeneration

The tool should avoid unnecessary regeneration when the output already exists.

Example:

```bash
listenforge generate 001.md
```

If the corresponding MP3 already exists, skip it or clearly report that it already exists.

Support:

```bash
listenforge generate 001.md --force
```

and:

```bash
listenforge generate-all --force
```

`--force` means regenerate existing output files.

This behavior must also work with custom `--input` and `--output` paths.

---

# 10. List Command

Support:

```bash
listenforge list
```

It should use the default:

```text
input = ./input
output = ./output
```

Also support:

```bash
listenforge list \
  --input ./lessons \
  --output ./generated-audio
```

Example output:

```text
ID    TITLE              LEVEL    STATUS
001   Job Interview      B1       GENERATED
002   Daily Meeting      B1       GENERATED
003   Database Problem   B2       NOT GENERATED
004   Code Review        B2       GENERATED
```

---

# 11. CLI Help

The CLI must provide:

```bash
listenforge --help
```

and command-specific help:

```bash
listenforge generate --help
```

```bash
listenforge generate-all --help
```

```bash
listenforge list --help
```

The help output must clearly document:

```text
--input <PATH>
--output <PATH>
--force
```

where applicable.

---

# 12. Examples That MUST Work

### Default single generation

```bash
listenforge generate 001.md
```

### Custom paths

```bash
listenforge generate 001.md \
  --input ./lessons \
  --output ./audio
```

### Default batch generation

```bash
listenforge generate-all
```

### Custom batch generation

```bash
listenforge generate-all \
  --input ./lessons \
  --output ./audio
```

### Generate directly to an SD card

Example:

```bash
listenforge generate-all \
  --input ./lessons \
  --output /Volumes/SDCARD/English
```

The tool must not assume that input and output are inside the project directory.

---

# 13. Path Validation

The tool must provide clear errors for invalid paths.

Examples:

```text
Error: Input directory does not exist:
./lessons
```

```text
Error: Input file does not exist:
./lessons/001.md
```

```text
Error: Output directory cannot be created:
./audio
```

The tool should create the output directory automatically when possible.

---

# 14. Important Design Principle

The input/output locations must NOT be hard-coded.

The effective paths are:

```text
INPUT  = --input  if provided, otherwise ./input
OUTPUT = --output if provided, otherwise ./output
```

The same rule must be consistently applied to:

* `generate`
* `generate-all`
* `list`
* any future commands that operate on lessons or generated audio

---

# 15. Intended Workflow

The main workflow is:

```text
AI generates Markdown lessons
        ↓
lessons/
├── 001.md
├── 002.md
├── 003.md
└── ...
        ↓
listenforge generate-all
        ↓
output/
├── 001.mp3
├── 002.mp3
├── 003.mp3
└── ...
        ↓
Copy to MP3 player / microSD
```

But the user must also be able to redirect the output wherever desired:

```bash
listenforge generate-all \
  --input ./lessons \
  --output /Volumes/SDCARD/English
```

This allows ListenForge to generate audio **directly onto an SD card or external storage device**.

---

# Implementation Freedom

Do not prescribe the implementation architecture.

You should determine:

* programming language
* CLI framework
* project structure
* Markdown parser
* TTS provider
* audio processing system
* FFmpeg usage
* configuration system
* testing
* packaging
* installation
* error handling details

First analyze this specification and propose an implementation plan.

Then implement the tool.

Do not change the CLI contract or input/output semantics without explaining why.
