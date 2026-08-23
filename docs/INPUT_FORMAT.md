# Input Format

One lesson is one Markdown file. The format is a strict, versioned contract: the parser
does not guess. If a file does not match, it is rejected with the file path, lesson id,
section and line number.

## Skeleton

```markdown
---
schema_version: "1.0"
id: "001"
title: "Job Interview"
level: "B1"
topic: "career"
language: "en-US"
---

## Context

Vietnamese context goes here.

## Listening

English listening content goes here.

## Vocabulary

- `experience` — kinh nghiệm

## Notes

Metadata only; never spoken.
```

## Front matter

All six fields are required and must be non-empty.

| Field | Rule |
|---|---|
| `schema_version` | Must be `"1.0"`. Lets the format evolve without breaking old files. |
| `id` | Unique across the input directory. No path separators. |
| `title` | Shown by `listenforge list` and written to the ID3 title tag. |
| `level` | One of `A1` `A2` `B1` `B2` `C1` `C2`. |
| `topic` | Free text. Metadata; does not affect the audio. |
| `language` | Locale of the English content, e.g. `en-US`, `en-GB`, `en-AU`. |

Duplicate ids across a batch are an error, not a warning — two lessons claiming `001`
usually means a copy-paste mistake.

## Sections

| Section | Required | Spoken |
|---|---|---|
| `## Context` | yes | yes, in Vietnamese |
| `## Listening` | yes | yes, in English |
| `## Vocabulary` | no | no |
| `## Notes` | no | no |

Headings must be exactly `## Context`, `## Listening`, `## Vocabulary`, `## Notes`.
Aliases are **not** accepted — `## English`, `## Situation` and `## Words` are errors, not
synonyms. This is deliberate: silent aliasing makes a typo produce a subtly wrong MP3
instead of a clear failure. If a new name is ever needed, it gets a new
`schema_version`.

A required section that is present but empty is also an error.

### Context

Vietnamese. Prepares the learner: who is speaking, where, and why. It should **not** be a
sentence-by-sentence translation of the listening, and should not give away the answers.

Paragraph breaks are preserved; whitespace inside a paragraph is normalized.

### Listening

English only. Not translated, simplified, or grammar-corrected — what you write is what
gets spoken.

**Dialogue** uses `Speaker: text`, one paragraph per turn:

```markdown
## Listening

Interviewer: So, could you tell me about your experience with Java?

Candidate: Sure. I've been working with Java for about three years.
```

The label is not spoken; it selects the voice. Voices are assigned in **first-appearance
order**, so the first speaker always gets the first configured English voice — stable
across runs.

**Narration** needs no labels:

```markdown
## Listening

Yesterday, I had to investigate a performance problem in our database.
The API was becoming slower as the amount of data increased.
```

A label is only recognised when the evidence is strong: two or more distinct labels, or
every paragraph carrying one. That is what keeps a sentence like

```text
There was one thing we missed: the index on the orders table.
```

from being parsed as a speaker named "There was one thing we missed".

### Vocabulary

```markdown
## Vocabulary

- `experience` — kinh nghiệm
- `be responsible for` — chịu trách nhiệm về
```

Markdown bullet, phrase first, Vietnamese meaning second, separated by an em dash (`—`).
Backticks are optional. This section is **not** in the MP3 — it is reference data,
returned as structured output and shown by tooling.

## Inline Markdown

`**bold**`, `_italic_` and `` `code` `` are accepted inside prose and stripped before
synthesis, so `**Interviewer:**` is recognised as a speaker label and no `*` or `_` ever
reaches the voice. Plain text is still preferred.

## What belongs here, and what does not

The lesson file describes **what to learn**. Voices, speeds, pause lengths and repeat
counts describe **how to render it**, and live in `config/listenforge.toml` — never in
front matter. Keeping them apart means you can retune every lesson's pacing by editing
one file.

## Example errors

```text
Error parsing:
input/003.md

Lesson ID: 003
Section: Vocabulary

Invalid vocabulary item on line 27

Expected:
- `phrase` — meaning
```

```text
Error parsing:
input/004.md

Lesson ID: 004

Unknown section '## English'. Allowed: ## Context, ## Listening, ## Vocabulary, ## Notes on line 18

Aliases are not accepted; see lesson-format-prompt.md §11.
```
