# Proposal Director - Music Video Pipeline

## When To Use

You are turning the `brief` into a `proposal_packet` + `decision_log`.
This stage covers mv-storyboard Step 3 (narrative style matching) and
Step 4 (character matching), plus the OpenMontage-MV-side decisions:
music plan, provider availability confirmation, and delivery shape.

Authoritative Layer 3 reference: `.agents/skills/mv-storyboard/SKILL.md`
Step 3-4 and `assets/narrative-style-guide.md`. Follow them exactly —
do not restate or improvise their rules.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Layer 3 | `.agents/skills/mv-storyboard/SKILL.md` Step 3-4 | Matching rules |
| Layer 3 | `.agents/skills/mv-storyboard/assets/narrative-style-guide.md` | 7 narrative styles, conflict priority, empty-shot library |
| Library | `character_library/` (fallback: `人物库/`) | Character MD files + PNG reference images |
| Schema | `schemas/artifacts/proposal_packet.schema.json`, `decision_log.schema.json` | Artifact validation |

## Process

### 1. Match Narrative Style (Step 3)

Apply the SKILL.md Step 3 matching table (songStyle + emotionalTone +
tempo + structure → one of the 7 narrative styles). On conflicting
signals, use the priority order in `narrative-style-guide.md`. If the
user passed a `narrative_override`, honor it and record the override in
`decision_log`.

### 2. Match Characters (Step 4)

Read the character library at `character_library/` in the repo root; if
missing, fall back to `人物库/`. Character MD format, the "适配歌曲风格"
matching field, and the matching priority are all defined in SKILL.md
Step 4 — cite the matched fields as justification. Users may also
supply custom characters in the SKILL.md custom format.

If a matched character MD references a PNG (e.g. `015.png`) that exists,
record its path — the assets stage binds it via reference-image
generation for cross-shot consistency (M4). No image → plain text
prompts (original behavior).

### 3. Music Plan (MANDATORY)

The MV soundtrack is the original song. The ASS file carries lyrics
only — no audio. Per AGENT_GUIDE "Music Plan (Mandatory)":

- Ask the user for the song audio file (check `music_library/` first,
  or a user-provided path).
- No audio available → downgrade delivery to **storyboard-only** and
  say so explicitly in the proposal. Never let this surface first at
  the assets stage.

### 4. Provider Confirmation (MANDATORY)

This project has a single video provider: `yinghe_video`. Do NOT
hardcode its availability — check the registry that the tool is
discovered and its dependencies (API key) are satisfied. If it is
unavailable, surface the blocker per "Escalate Blockers Explicitly"
(there is no fallback provider to swap to). Record a `provider_selection`
entry in `decision_log` anyway — single-option decisions are still
audited.

`render_runtime` is always `ffmpeg` (stitch + song audio + ASS burn-in);
record a `render_runtime_selection` entry noting ffmpeg as the only
runtime.

The storyboard's `seedancePrompt` fields follow the Seedance 2.0
eight-element formula — yinghe_video is a Seedance route, so the
prompt structure applies directly.

### 5. Delivery Shape

Decide and record: **storyboard-only** (stop after the storyboard
stage) vs **full MV**. For full MV, state the expected shot count (≤23)
and per-shot durations (4-15s) so the user knows the generation scope
before approving.

## Outputs

- `proposal_packet`: narrative style + storyline concept, matched
  characters (with reference image paths when found), music plan,
  delivery shape, generation scope.
- `decision_log`: narrative style match (with evidence), character
  match, provider selection, `render_runtime_selection`, delivery
  shape, music plan resolution.

## Checkpoint

Write `checkpoint_proposal.json` per checkpoint-protocol with both
artifacts embedded. Fully automatic — no human wait.
