# Compose Director - Music Video Pipeline

## When To Use

You are executing `edit_decisions` into the final MV file and producing
`render_report` + `final_review`. Compose here is ffmpeg-led end to end:
stitch the shot clips, lay the song audio, burn the ASS karaoke subtitles.
There is no composition-runtime pass — `render_runtime` is always `ffmpeg`.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Input | `edit_decisions`, `asset_manifest` | Assembly plan + clips |
| Input | original ASS file path (from edit_decisions subtitle plan) | Karaoke burn-in source |
| Tools | `video_stitch`, `audio_mixer` (required); `color_grade` (optional) | Assembly |
| Schema | `schemas/artifacts/render_report.schema.json`, `final_review` | Artifact validation |

## Process

### 1. Stitch The Visual Track

`video_stitch` the clips in shot order with the planned transitions.
Trim tails where edit_decisions says so. Mute/strip clip-native audio.

### 2. Lay The Song Audio

`audio_mixer`: the song audio as the single track from t=0. Verify the
stitched visual runtime equals the song duration before mixing.

### 3. Burn Karaoke Subtitles (M5)

Burn the ORIGINAL ASS file over the assembled video (ffmpeg
`subtitles=`/`ass=` filter — the ASS carries its own per-word karaoke
timing and styling; do not regenerate or re-time it). Skip only on the
user's recorded opt-out. This is capability the original plugin never
had — generation stays subtitle-free, delivery carries the karaoke.

### 4. Optional Grade

`color_grade` only if the storyboard's visualTone calls for a uniform
pass across mixed shots; keep it subtle and note it in the report.

### 5. Verify & Report

- ffprobe the output: total duration == song duration (±0.1s)
- Spot-check A/V sync at 3+ shot boundaries and subtitle timing at 2+
  lyric lines
- Write `render_report` (paths, runtime, tool versions, durations) and
  `final_review` per its contract

## Checkpoint

Write `checkpoint_compose.json` per checkpoint-protocol with both
artifacts embedded. Fully automatic — no human wait.
