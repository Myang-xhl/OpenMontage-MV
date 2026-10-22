# Reviewer — Meta Skill

## When to Use

After completing any pipeline stage's work — before checkpointing. You are the quality gate between "work done" and "work accepted." This skill replaces the Python reviewer class with an instruction-driven self-review protocol.

Every stage gets reviewed. No exceptions. The review quality determines whether the final video is worth watching.

## Critique Quality (CHAI Rules)

> Findings ≠ critiques. A finding identifies a problem; a critique tells the next stage how to fix it. The CMU/Harvard CHAI study ("Building a Precise Video Language with Human-AI Oversight", arXiv 2604.21718v2) showed that critique quality, measured on three axes, directly governs downstream output quality. Apply all three to every reviewer pass.
>
> **Accurate.** Every finding must reference a concrete artifact field, line number, or visible asset frame. Forbid hallucinated criticism — if you cannot point to where the problem is, you are guessing.
>
> **Complete.** A reviewer pass that catches one mistake while missing a second is worse than scoring "needs another pass" and continuing. If you find one critical issue, scan for the rest of the same class before returning. Pattern-match: where else in this artifact could the same mistake be hiding?
>
> **Constructive.** Every "critical" finding MUST propose a concrete fix, not just identify the problem. "Caption is wrong" → "Caption says 'man on the right'; the man is on the left of the frame. Replace with 'the man on the left of the frame.'" If you cannot propose a fix, label the finding as "investigation" not "critical."
>
> Removing any of these three properties measurably hurts pipeline output. The reviewer is the choke point — be rigorous.

## Protocol

### Step 1: Load Review Context

Before reviewing, gather:
1. **Review focus items** from the pipeline manifest for this stage (`review_focus` field)
2. **Success criteria** from the manifest for this stage (`success_criteria` field)
3. **Active playbook** quality rules
4. **The artifact** produced by the stage

### Step 2: Schema Validation

First, the non-negotiable check:
- Validate the artifact against its JSON schema (`schemas/artifacts/<name>.schema.json`)
- If schema validation fails, this is a **critical** finding — fix immediately, do not proceed

### Step 3: Review Against Focus Items

For each `review_focus` item from the manifest:
1. Evaluate the artifact against this specific criterion
2. Assign a severity:
   - **critical** — Must fix before proceeding. The artifact is broken, incomplete, or dangerously wrong. **Per CHAI rules, every critical finding MUST carry a `proposed_fix` (concrete replacement text, exact field value, or specific corrective action). A critical finding without a proposed fix is downgraded to `investigation`.**
   - **suggestion** — Should fix. Improves quality significantly but doesn't block progress. **Suggestions MUST carry a `proposed_change` describing how to improve.**
   - **nitpick** — Could fix. Minor polish that's nice-to-have. May stand alone without a proposed change.
   - **investigation** — A real concern but you cannot pinpoint the fix. Surface it for the next round; do not block on it.
3. Write a specific, actionable finding (not vague)

**Good finding:** "Section 3 narration is 180 words for a 10-second window — that's 1080 wpm, impossible to speak. Cut to 25 words."
**Bad finding:** "Script might be too long."

### Step 4: Cross-Check Against Playbook

If a style playbook is active, verify:
- [ ] Color references match playbook palette
- [ ] Transition types are in the playbook's allowed set
- [ ] Pacing rules are respected (min/max durations)
- [ ] Asset descriptions include playbook style cues
- [ ] Quality rules are not violated

Each violation is a **suggestion** severity finding.

### Step 4b: Taste Direction Review

If `proposal_packet.production_plan.taste_profile` or the active playbook's `taste_profile` exists, verify:
- [ ] `design_read` explains the brief, audience, and delivery promise; it is not just "modern/clean/professional"
- [ ] `visual_variance`, `motion_intensity`, and `information_density` are reflected in scene layout, pacing, callout density, and asset prompts
- [ ] `reference_strategy` is present when atelier work, AI image/video, product/brand visuals, or mood boards depend on visual nuance
- [ ] Listed `anti_patterns` are actually avoided
- [ ] Quality gates are concrete enough for the next stage to enforce

At proposal stage, a missing `taste_profile` is a **suggestion** for preset/low-stakes work and a **critical** finding for atelier, product/brand, launch, hero, or custom-playbook work. At scene_plan/edit/compose, treat dial violations as **suggestion** unless they break the approved delivery promise.

### Step 5: Evaluate Success Criteria

For each `success_criteria` item from the manifest:
- Is the criterion met? (yes/no/partial)
- If not met, create a **critical** finding

### Step 6: Make a Decision

Count findings by severity:

| Scenario | Action |
|----------|--------|
| 0 critical, any suggestions/nitpicks | **Pass** — proceed to checkpoint. Note suggestions for the record. |
| 1+ critical findings | **Revise** — fix all critical findings, then re-review (max 2 rounds). |
| After 2 revision rounds, still critical | **Pass with warnings** — proceed anyway, note unresolved issues. Never block indefinitely. |

### Step 7: Record Review

Structure your review as:

```
## Review: [stage_name] — Round [N]

**Decision:** PASS / REVISE / PASS_WITH_WARNINGS

### Findings

1. [CRITICAL] Title of finding
   - Description: What's wrong
   - Action: What to fix
   - Status: pending / fixed / accepted / deferred

2. [SUGGESTION] Title of finding
   - Description: What could be better
   - Action: How to improve
   - Status: pending / accepted / deferred

### Summary
- Critical: N (N fixed)
- Suggestions: N
- Nitpicks: N
- Playbook violations: N
- Success criteria met: N/M
```

## Key Principles

1. **Be specific, not vague.** "The hook is weak" is useless. "The hook asks a question but doesn't create urgency — try leading with the surprising stat from key_point #2" is actionable.

2. **Critical means critical.** Don't inflate severity. A missing schema field is critical. A slightly wordy paragraph is a suggestion. A comma splice is a nitpick.

3. **Two rounds max.** The goal is shipping, not perfection. After two revision rounds, pass with warnings and move on. Perfectionism kills pipelines.

4. **Review the artifact, not the process.** You're checking the output, not how it was produced. If the brief is compelling, it doesn't matter if the agent used an unusual approach.

5. **Playbook is law.** If the playbook says "no more than 3 colors on screen," that's not a suggestion — it's a constraint. Violations are always flagged.

## Stage-Specific Review Guidance

| Stage | What matters most |
|-------|-----------------|
| idea | ASS parsed cleanly (encoding, no tag residue), section map grounded in the three signals, style judgments cite lyric evidence |
| proposal | Narrative style + character match evidence, music plan resolved, provider confirmed, decision log started |
| storyboard | ≤23 shots / integer 4-15s / continuous timeline, eight-element prompts, one camera movement per shot, constraint packs appended |
| assets | Clip existence + duration match, character consistency across shots |
| edit | Storyboard timeline coverage, song audio at t=0, ASS subtitle plan |
| compose | Runtime == song duration, A/V sync at shot boundaries, ASS karaoke burn correct |
| publish | Delivery package complete (MV + storyboard.md + storyboard.json), metadata matches song |

## Decision Log Review

Run at **every stage** after proposal. The decision log (`schemas/artifacts/decision_log.schema.json`) is a cumulative audit trail.

### Checks:
1. **Existence**: Does the checkpoint reference a `decision_log_ref`? If not after proposal stage, flag as **SUGGESTION**.
2. **Coverage**: Does every major choice have an entry? Key decisions that MUST be logged:
   - Narrative style match (with evidence)
   - Character match
   - Provider confirmation (`yinghe_video` availability)
   - `render_runtime_selection` (always `ffmpeg`)
   - Music plan resolution (song audio source)
   - Delivery shape (storyboard-only vs full MV)
   - Any downgrade (e.g., full MV → storyboard-only)
3. **Quality**: Each decision should have:
   - At least 2 `options_considered` (not just the one picked)
   - A `reason` that isn't boilerplate ("best option" is not a reason)
   - Correct `confidence` (0.0–1.0) — flag if everything is 1.0 (unrealistic)
4. **User visibility**: Decisions marked `user_visible: true` should be ones the user would actually care about (not internal routing)

### Severity:
- Missing decision log after proposal: **SUGGESTION** (first time), **CRITICAL** (if still missing at edit stage)
- Decision with only 1 option considered: **SUGGESTION** — "Log rejected alternatives for auditability"
- All decisions at confidence 1.0: **SUGGESTION** — "Unrealistic confidence — at least provider selection involves tradeoffs"

## Storyboard Variety & Runtime Review

Run at **storyboard** and **edit** stages. Prevents the "every shot looks the same" failure mode.

### Checks:
1. **Shot variety** (storyboard): do consecutive shots vary shot size / angle / scene?
   - Long runs of identical shot grammar → **SUGGESTION** — "Vary the visual grammar across shots"
2. **Empty shots earn their place** (storyboard): 空镜 must serve the narrative (intro/interlude/outro breathing room), not filler → **SUGGESTION**
3. **Runtime lock** (edit and compose stages):
   - `render_runtime` in edit_decisions must be `ffmpeg` — the only runtime in this project
   - Any other value without a logged `render_runtime_selection` decision → **CRITICAL**

## Final Self-Review Review

Run at **compose** and **publish** stages. Ensures the agent reviewed the actual rendered output.

### At compose stage:
1. **Existence**: Does a `final_review` artifact exist alongside the `render_report`?
   - If missing: **CRITICAL** — "Compose produced a render_report but no final_review. The agent must inspect the rendered output before presenting it."
2. **Status check**: What is `final_review.status`?
   - `pass` → OK, proceed
   - `revise` → The agent should have fixed issues before presenting. If the pipeline continued anyway: **CRITICAL** — "Self-review found revise-worthy issues but the agent presented anyway."
   - `fail` → The pipeline MUST NOT proceed. If it did: **CRITICAL**
3. **Check completeness**: All 5 required checks must have data:
   - `technical_probe` must show a valid container with plausible duration/resolution
   - `visual_spotcheck` must have `frames_sampled >= 4`
   - `audio_spotcheck` must report narration/music presence
   - `promise_preservation` must confirm `delivery_promise_honored`
   - `subtitle_check` must report presence/absence
   - Any check with missing data: **SUGGESTION** — "Self-review check [X] has incomplete data"
4. **Promise preservation**: If `promise_preservation.silent_downgrade_detected` is true: **CRITICAL** — "Self-review detected silent downgrade from motion-led to still-led."

### At publish stage:
1. Verify that `final_review` was passed through as a required artifact
2. If `final_review.status` is not `pass`: **CRITICAL** — "Cannot publish with a non-passing self-review"
3. If `final_review.issues_found` is non-empty and `recommended_action` is not `present_to_user`: **SUGGESTION** — "Self-review found issues; verify they were resolved before publishing"
