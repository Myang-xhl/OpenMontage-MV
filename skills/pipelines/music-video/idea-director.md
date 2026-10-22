# Idea Director - Music Video Pipeline

## When To Use

You are turning a user-supplied ASS karaoke lyric file into the `brief`
artifact for a music video. This stage covers mv-storyboard Step 1 (ASS
parsing, via the `ass_parser` tool) and Step 2 (song structure analysis,
your cognitive task).

Authoritative Layer 3 reference: `.agents/skills/mv-storyboard/SKILL.md`
— follow its steps exactly; this document only maps them onto the
OpenMontage stage protocol. Do not restate or improvise its rules.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Tool | `ass_parser` | Deterministic Step 1: encoding, Dialogue extraction, tag stripping, singer mapping, timing |
| Layer 3 | `.agents/skills/mv-storyboard/SKILL.md` Step 1-2 | Parsing spec and section-analysis rules |
| Schema | `schemas/artifacts/brief.schema.json` | Artifact validation |
| Meta | `skills/meta/reviewer.md` | Self-review pass |

## Process

### 1. Parse The ASS File (Step 1 — tool call)

Call `ass_parser` with `input_path` pointing at the user's `.ass` file.
The tool implements SKILL.md Step 1 verbatim (UTF-8 → GBK fallback,
`[Events]` Dialogue regex, karaoke `{\K28}`/`{\k28}` + override tag
stripping, Style → singer mapping, `H:MM:SS.cs` → seconds). Its output
gives you: `lines` (start/end/singer/text/raw), `total_duration`,
`singers`, and `gaps` (intro + >3s interludes).

If the tool reports garbled or empty output, surface the encoding
problem to the user instead of guessing.

### 2. Analyze Song Structure (Step 2 — cognitive)

Apply SKILL.md Step 2 to the parsed lines:

- **2.1 Section detection** using the three signals — timing gaps (the
  tool's `gaps` list), lyric repetition, singer changes.
- **2.2 Section labels** — `intro/verseA/verseB/preChorus/chorus/bridge/interlude/outro`
  per the table in SKILL.md.
- **2.3 Style + emotion judgment** — the 4-dimension analysis
  (语言/节奏/主题/歌手配置) producing songStyle, emotionalTone,
  language, tempo, and the emotional arc.

Every judgment must cite lyric evidence — the reviewer checks this.

### 3. Write The Brief

Produce a schema-valid `brief`:

- `title`: song name (from the ASS filename or user input)
- `hook`: the emotional core of the song in one line
- `key_points`: the section map summarized as beats
- `tone`: emotionalTone; `style`: songStyle
- `target_platform`: per user intent (default `generic`)
- `target_duration_seconds`: `total_duration` from ass_parser
- `reference_material`: the ASS file path (plus reference MV if given)
- `metadata`: the full Step 2 output structure — `songStyle`,
  `emotionalTone`, `language`, `duration`, `tempo`, `sections`
  (typed, timed, with singer), `emotionalArc`, and the `ass_parse`
  summary (line_count, singers, encoding, gaps)

## Checkpoint

Write `checkpoint_idea.json` per `skills/meta/checkpoint-protocol.md`
with the `brief` artifact embedded. This pipeline runs fully automatic
(`human_approval_default: false`) — checkpoints feed the board, they do
not wait for a human.

## Self-Review

Before completing, verify against the stage `review_focus`:

- Encoding correct, lyrics complete, no tag residue
- Section structure grounded in all three signals
- Style/emotion judgments carry lyric evidence
