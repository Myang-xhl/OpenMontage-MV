# Publish Director - Music Video Pipeline

## When To Use

You are packaging the finished MV for delivery and producing
`publish_log`. This is the terminal stage.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Input | `render_report`, `final_review` | What was rendered, verified how |
| Input | `storyboard` artifact (optional) | Deliverable companion files |
| Schema | `schemas/artifacts/publish_log.schema.json` | Artifact validation |

## Process

### 1. Assemble The Delivery Package

Three deliverables, all under `projects/<id>/renders/` (or the export
path the user specified):

1. The final MV file (from `render_report`)
2. `{songName}_storyboard.md` — the human-readable storyboard
3. `storyboard.json` — the machine-readable storyboard

Verify all three exist on disk before logging. If delivery shape was
storyboard-only, the pipeline should have finished at the storyboard
stage — reaching publish without a render is a governance error to
surface, not to paper over.

### 2. Metadata

Write delivery metadata consistent with the song and narrative style:
song name, duration, narrative style, shot count, provider used,
generation date.

### 3. Publish Log

Produce the schema-valid `publish_log` listing every delivered file
with its path, size, and checksum where the schema asks for one.

## Checkpoint

Write `checkpoint_publish.json` per checkpoint-protocol with
`publish_log` embedded. Fully automatic — the completion summary to the
user replaces any approval gate.
