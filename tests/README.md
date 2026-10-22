# Tests

Test cases referencing removed modules (cost_tracker governance, deleted
providers, video_compose, selectors) were dropped with them. Re-derive tests
from the retained surface:

- **contracts**: every tool in `tools/` satisfies the `BaseTool` contract
  (identity fields, schemas, dependency declarations, inheritance) — the
  registry smoke test (`discover()` finds exactly 6 tools) covers the basics.
- **qa**: `ass_parser` against a real `.ass` file; `video_stitch` + `audio_mixer`
  + ASS burn-in against fixture clips; `yinghe_video` against the live API.
- **pipeline**: `lib/pipeline_loader` validates `pipeline_defs/music-video.yaml`;
  `lib/checkpoint` write/read/gate round-trip under `projects/`.
