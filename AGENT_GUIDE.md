# OpenMontage-MV - Agent Guide

Start here. This is the complete operating guide and agent contract for OpenMontage-MV.

OpenMontage-MV is a single-purpose fork of OpenMontage: it does exactly one thing —
turn an ASS karaoke lyric file into a full music video. One pipeline, one video
provider, one render runtime (ffmpeg).

```
User supplies song.ass (+ song audio)
        |
        v
Agent reads pipeline manifest (pipeline_defs/music-video.yaml)
        |
        v
idea -> proposal -> storyboard -> assets -> edit -> compose -> publish
        |
        v
projects/<project-id>/renders/final.mp4 (+ storyboard.md/json)
```

**The AI agent IS the intelligence.** Python provides tools and persistence only.
No orchestration logic, creative decisions, or review logic lives in Python code.

## Rule Zero — All Production Goes Through the Pipeline

**Every MV production request MUST go through the `music-video` pipeline. No exceptions.**

1. **Read the pipeline manifest.** `pipeline_defs/music-video.yaml` — know the stages,
   tools, and quality gates.
2. **Run preflight.** Confirm `yinghe_video` is discovered and available via the registry.
3. **Execute stage by stage.** For EACH stage, read the stage director skill
   (`skills/pipelines/music-video/<stage>-director.md`) BEFORE doing any work in that stage.
4. **Read Layer 3 skills before calling tools.** Before `yinghe_video`, read
   `.agents/skills/seedance-2-0/`. Before writing any storyboard shot, read ALL of
   `.agents/skills/mv-storyboard/` per the storyboard-director.

**Do NOT:**
- Write ad-hoc Python scripts to call tools directly
- Skip the pipeline and go straight to API calls
- Generate assets without reading the stage director skill first
- Write a storyboard without reading the mv-storyboard Layer 3 documents
- Bypass preflight, checkpoints, or review

The intelligence is in the skills, not in improvised code.

## The Pipeline

`idea -> proposal -> storyboard -> assets -> edit -> compose -> publish`

| Stage | Director Skill | Canonical output | Core quality bar |
|------|---------------|------------------|------------------|
| `idea` | `idea-director.md` | `brief` | ASS parsed cleanly (encoding, no tag residue); section map grounded in gaps/repetition/singers; style judgments cite lyric evidence |
| `proposal` | `proposal-director.md` | `proposal_packet` + `decision_log` | Narrative style + characters matched per SKILL.md Step 3-4; music plan resolved; provider confirmed; delivery shape explicit |
| `storyboard` | `storyboard-director.md` | `storyboard` | ≤23 shots, integer 4-15s each, continuous timeline; eight-element seedancePrompt per shot; dual-format output (json + md) |
| `assets` | `asset-director.md` | `asset_manifest` | One clip per shot, duration matches storyboard, character consistency via reference images |
| `edit` | `edit-director.md` | `edit_decisions` | Clips on storyboard timeline; song audio at t=0; ASS subtitle plan confirmed |
| `compose` | `compose-director.md` | `render_report` + `final_review` | Runtime == song duration (±0.1s); A/V sync at shot boundaries; ASS karaoke burned from the ORIGINAL file |
| `publish` | `publish-director.md` | `publish_log` | Delivery package complete (MV + storyboard.md + storyboard.json) |

The pipeline runs **fully automatic** (`human_approval_default: false` on every
stage) — checkpoints feed the Backlot board, they do not wait for a human.
Storyboard-only delivery (stop after `storyboard`) is supported when the user
just wants the shot script or no song audio is available.

## Mandatory Preflight

Before any production work, confirm the single video provider is real:

```bash
python -c "
from tools.tool_registry import registry
registry.discover()
tool = registry.get('yinghe_video')
info = tool.get_info()
print('status:', info.get('status'))
print('dependencies:', info.get('dependencies'))
"
```

- If `yinghe_video` is unavailable (missing API key), **stop and tell the user**.
  There is no fallback provider in this project — do not improvise one.
- Also verify `ffmpeg` is on PATH (video_stitch, audio_mixer, ASS burn-in all need it).

## Project Directory Convention

Every production run creates a project workspace under `projects/`. This directory
is gitignored — all generated assets are regenerable.

```
projects/<project-name>/
├── artifacts/          # JSON artifacts from each stage (brief, storyboard, etc.)
├── assets/
│   └── video/          # Generated shot clips (shot_01.mp4 ...)
└── renders/
    └── final.mp4       # Final MV (the deliverable)
```

**Naming convention**: kebab-case derived from the song name (e.g., `taiyang-mv`).

At pipeline initialization:

1. **Initialize the workspace**: `python -c "from lib.checkpoint import init_project; init_project('<project-id>', title='<Title>', pipeline_type='music-video')"` — creates the layout and writes `project.json`.
2. **Open the board**: run `python -m backlot open <project-id>`. If the command fails, continue the production — the board is an observer, never a blocker.

All tools must write outputs under `projects/<project-id>/` — always pass an
explicit `output_path`. Assets written elsewhere are invisible to the board.

## Music Plan (Mandatory)

The MV soundtrack is the original song. The ASS file carries lyrics only — no audio.

1. Check `music_library/` first — the user may have dropped the song there
   (`music_library` tool lists tracks).
2. Otherwise ask the user for the song audio file path.
3. **No audio available -> downgrade delivery to storyboard-only** and say so
   explicitly in the proposal. Never let this surface first at the assets stage.

Record the music plan in the proposal artifact.

## Decision Communication Contract

For any meaningful production decision, communicate the decision before acting.

### Announce Before Execution

Before any generation call, state: the exact tool name, the provider, the reason,
and whether it is a sample or a batch run.

### Escalate Blockers Explicitly

When a blocker occurs, surface it immediately:

1. What was attempted
2. What failed
3. Whether the issue is auth, provider access, tool bug, or prompt/design quality
4. What options exist next
5. Which option you recommend, with reasoning

With a single provider, "switch provider" is NOT an option — the options are:
fix the key/config, wait and retry, or downgrade to storyboard-only delivery.
Do not execute any substitute path until the user approves.

### Re-log Changed Decisions (Binding)

The `decision_log` is append-only history. When a logged choice changes mid-run,
append a NEW entry with the SAME `category` AND `subject`, moving the superseded
option into `options_considered`. Never silently mutate the old entry.

### No Unilateral Substitutions

If the approved path is blocked, you may investigate alternatives but may not
execute them without user approval. This applies especially to provider-side
workarounds and still-image animatics in place of true motion clips.

## Reviewer Protocol

Self-review after every stage execution, before checkpointing, using
`skills/meta/reviewer.md`:

- Load `review_focus` items from the pipeline manifest for the current stage.
- Maximum two review rounds; after that, pass with warnings and move on.
- Findings: critical (must fix), suggestion (should fix), nitpick (nice-to-have).

## Checkpoint Protocol

Per `skills/meta/checkpoint-protocol.md`:

- Checkpoints live at `projects/<project_id>/checkpoint_<stage>.json`.
- `status`: `completed` | `failed` | `awaiting_human` | `in_progress`.
- Write `in_progress` on entering each stage; during `assets`/`compose`, refresh
  `metadata.partial_progress` after each completed shot — this powers the board's
  live progress.
- `completed` checkpoints must include the stage's canonical artifact, validated
  against `schemas/artifacts/`.
- Superseded checkpoints are archived to `projects/<project_id>/history/`.

## Layer Map

```
Layer 3: .agents/skills/          External craft knowledge
         mv-storyboard/           The 7-step storyboard method (READ ALL before storyboarding)
         seedance-2-0/            Seedance prompt engineering (yinghe is a Seedance route)
         ffmpeg/                  Composition debugging reference
              ^
              | referenced from director skills
              |
Layer 2: skills/                  OpenMontage-MV conventions
         pipelines/music-video/   7 stage director skills (HOW each stage works)
         meta/                    reviewer + checkpoint-protocol
              ^
              |
Layer 1: tools/ + pipeline_defs/  Executable capabilities + the manifest
```

Reading order per stage: manifest -> director skill (Layer 2) -> Layer 3 craft docs
-> tool call. Prefer skills over source code for tool usage; read source only for
debugging and audits.

## Tool Contract

- Every tool inherits `BaseTool`; call via `.execute(params_dict)` which returns
  `ToolResult` with `.success`, `.data`, `.error`.
- Tool discovery flows through `tools/tool_registry.py`, never ad-hoc imports.
- Tool classes use PascalCase without a "Tool" suffix (e.g. `YingheVideo`).

Tool inventory (the whole toolbox):

| Tool | Capability | Used at |
|------|-----------|---------|
| `ass_parser` | ASS parsing (encoding, singers, gaps) | idea |
| `music_library` | List user-dropped song audio | proposal |
| `yinghe_video` | Seedance video generation (ONLY provider) | assets |
| `video_stitch` | Clip concat/trim + ASS subtitle burn-in | compose |
| `audio_mixer` | Song audio track assembly | compose |
| `color_grade` | Optional uniform grade (ffmpeg LUTs) | compose |

## Character Library

`character_library/` holds character MD files + PNG reference images used at the
proposal stage (SKILL.md Step 4 matching). Users may add custom characters in the
format defined by `.agents/skills/mv-storyboard/SKILL.md`. When a matched character
has a PNG, bind it at the assets stage for cross-shot consistency.

## What Not To Do

- **Do not bypass the pipeline.** See Rule Zero.
- **Do not call `yinghe_video` without reading `seedance-2-0/` first.**
- **Do not skip stage director skills.**
- Do not weaken the storyboard hard limits (≤23 shots, integer 4-15s) — a schema
  rejection is a bug in your storyboard, never a reason to loosen the schema.
- Do not regenerate or re-time the ASS subtitles — burn the ORIGINAL file at compose.
- Do not silently swallow provider failures — escalate per the contract above.
- Do not reintroduce a second video provider or a composition runtime without
  updating this guide and the manifest together.
