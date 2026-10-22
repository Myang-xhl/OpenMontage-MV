# Edit Director - Music Video Pipeline

## When To Use

You are turning the `storyboard` + `asset_manifest` into
`edit_decisions`: the exact assembly plan the compose stage executes.
The MV edit is unusual among pipelines — the timeline is already fixed
by the lyrics, so this stage is verification and assembly ordering, not
creative re-cutting.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Input | `storyboard` (timeline, transitions), `asset_manifest` (clip paths) | What to assemble |
| Input | `proposal_packet` | Music plan (song audio path) |
| Schema | `schemas/artifacts/edit_decisions.schema.json` | Artifact validation |

## Process

### 1. Arrange Clips On The Storyboard Timeline

Order clips strictly by `shotNumber`. Each clip occupies exactly
[startTime, endTime] from its shot — the storyboard timeline is
authoritative (it was derived from lyric timestamps). If a generated
clip runs long, plan a trim from the tail; never re-time lyrics to fit
footage.

### 2. Align The Song Audio

The full-length song audio (from the proposal's music plan) is the ONE
audio track, aligned to t=0. No ducking, no mixing with clip audio —
plan to strip/mute any audio the generated clips carry. Verify: last
shot's endTime == song duration.

### 3. Transitions

Carry each shot's `transition` field into the edit decisions (硬切 →
straight cut; 叠化/闪白/黑场/匹配剪辑 → the corresponding compose-level
transition). Keep the storyboard's pacing intent — do not add
transitions the storyboard didn't specify.

### 4. Subtitle Plan (M5)

Record the subtitle decision: burn in the ORIGINAL ASS file at compose
(karaoke per-word timing preserved). Note the ASS path from the brief.
If the user declined subtitles, record the opt-out explicitly.

### 5. Runtime

`render_runtime` is always `ffmpeg` in this pipeline — record it as
such in `edit_decisions` (stitch + song audio + ASS burn-in).

## Checkpoint

Write `checkpoint_edit.json` per checkpoint-protocol with
`edit_decisions` embedded. Fully automatic — no human wait.
