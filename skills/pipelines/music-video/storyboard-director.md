# Storyboard Director - Music Video Pipeline

## When To Use

You are turning the `brief` + `proposal_packet` into the `storyboard`
artifact. This stage covers mv-storyboard Step 5 (shot orchestration,
18 dimensions), Step 6 (Seedance prompt writing) and Step 7 (dual-format
output). This is the heart of the port — the original skill's entire
craft lives in the Layer 3 documents; read them before writing a single
shot.

Authoritative Layer 3 references (read ALL before starting):

- `.agents/skills/mv-storyboard/SKILL.md` Step 5-7 — shot division
  principles, the 18-dimension field table, continuity rules, the
  ≤23-shot reduction strategy, the eight-element prompt formula,
  the self-check checklist, and the 3 full prompt examples
- `.agents/skills/mv-storyboard/assets/camera-language-reference.md`
  — shot sizes, angles, movements, combination patterns, transitions
- `.agents/skills/mv-storyboard/assets/seedance-prompt-guide.md`
  — element word counts, keyword banks, the 5 mandatory constraint
  packs, action rules, DO/DON'T, shot templates
- `.agents/skills/mv-storyboard/assets/storyboard-template.md`
  — the Markdown output template ({{placeholders}})

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/storyboard.schema.json` | Machine validation (≤23 shots, integer 4-15s enforced) |
| Input | `brief` (sections, style, tone), `proposal_packet` (narrative style, characters, delivery shape) | Upstream decisions |

## Process

### 1. Orchestrate Shots (Step 5)

Divide the song timeline into shots per SKILL.md Step 5: section-driven
division, the narrative-style编排策略 from the proposal, empty shots
(空镜) for intro/interlude/outro, and continuity principles (scene,
outfit, lighting, emotional arc). Fill all 18 dimensions for every
shot. Hard limits (schema-enforced):

- **≤23 shots total** — apply the SKILL.md reduction strategy if over
- **Integer durations, 4-15 seconds each**
- **Timeline continuous**: shot N's endTime == shot N+1's startTime,
  covering 0 → song end with no gaps or overlaps

### 2. Write Seedance Prompts (Step 6)

For every shot, write `seedancePrompt` with the eight-element formula
from `seedance-prompt-guide.md`. Non-negotiables from the guide: one
camera movement per shot; emotion externalized as concrete body detail
(the 对照表); low-intensity continuous actions; the mandatory constraint
packs appended verbatim (画质包 + 稳定包 + 字幕兜底 + 水印Logo兜底,
plus 双胞胎兜底 on two-person shots); special-character rules.

Note: prompts say "保持无字幕" — that governs the *generation* layer.
Karaoke subtitles are burned in later at compose from the original ASS
(M5). Do not weaken the no-subtitle constraint here.

### 3. Dual-Format Output (Step 7, M1 paths)

Write both formats to canonical project paths:

- `projects/<id>/artifacts/storyboard.json` — the `storyboard` artifact,
  schema-validated. Fill `meta.provenance` (`generated_by`, `pipeline:
  "music-video"`, `tool_versions` incl. ass_parser, `seed_policy`).
  Leave `assetPath` null (assets stage backfills); set `referenceImages`
  from the proposal's character reference paths when present.
- `projects/<id>/artifacts/{songName}_storyboard.md` — rendered from
  `storyboard-template.md` with every {{placeholder}} resolved.

Only if the user explicitly asks: mirror a copy next to the ASS file
(original plugin behavior).

### 4. Self-Check (MANDATORY)

Run the SKILL.md self-check checklist item by item and record the pass
in the checkpoint notes. The stage `success_criteria` and the schema
enforce the same limits — treat a schema rejection as a bug in your
storyboard, never as a reason to loosen the schema.

## Delivery Note

If the proposal's delivery shape is **storyboard-only**, this stage's
output IS the deliverable: present both files to the user and stop the
pipeline here (record the early-finish in the checkpoint).

## Checkpoint

Write `checkpoint_storyboard.json` per checkpoint-protocol with the
`storyboard` artifact embedded. Fully automatic — no human wait.
