# Asset Director - Music Video Pipeline

## When To Use

You are generating one video clip per storyboard shot and producing the
`asset_manifest`. The original mv-storyboard skill ended at the script;
this stage is where OpenMontage turns it into footage (M10).

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Input | `storyboard` artifact | Shot list with seedancePrompt, duration, referenceImages |
| Input | `proposal_packet` / `decision_log` | Confirmed provider, delivery shape |
| Layer 3 | `.agents/skills/seedance-2-0/` | Provider-specific API knowledge (yinghe is a Seedance route) |
| Schema | `schemas/artifacts/asset_manifest.schema.json` | Artifact validation |

## Process

### 1. Confirm The Provider Route

Call `yinghe_video` directly — it is the only video provider in this
project. If it is unavailable at run time (missing key, outage),
surface the blocker per "Escalate Blockers Explicitly" — there is no
fallback provider to swap to.

### 2. Generate Shot By Shot

For each shot in `storyboard.shots`, in order:

1. **Reference images (M4)**: if `shot.referenceImages` is non-empty
   and the provider supports reference-conditioned generation (Seedance
   `reference_to_video`, ≤9 images), bind them to lock character
   identity. Otherwise rely on the text prompt alone (original
   behavior).
2. **Generate** with `prompt=shot.seedancePrompt`,
   `duration=shot.duration` (integer seconds, already 4-15 by schema),
   `output_path=projects/<id>/assets/video/shot_NN.mp4`.
3. **Verify** the clip exists and its ffprobe duration matches
   `shot.duration` (±0.5s tolerance); regenerate once on mismatch,
   then surface if still off.
4. **Backfill** `storyboard.shots[].assetPath` with the clip path and
   refresh `partial_progress` in the checkpoint so the board shows
   per-shot progress.

### 3. Write The Asset Manifest

Produce a schema-valid `asset_manifest` listing every clip (path, shot
number, duration, provider, seed when reported). Persist the
updated `storyboard` (with assetPath backfilled) to
`projects/<id>/artifacts/storyboard.json`.

## Review Focus Reminders

- Clip duration == storyboard shot duration, every shot
- Character consistency across shots (reference images when available)
- Actions low-intensity per the Seedance action rules

## Checkpoint

Write `checkpoint_assets.json` per checkpoint-protocol. Fully automatic
— refresh `partial_progress` after every shot rather than waiting.
