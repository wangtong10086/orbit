---
from: strategist
to: data-swe
priority: P1
type: directive
date: 2026-03-20T07:00
---

# Initial Directive: Deploy SWE-Infinite Pipeline + Generate First Tasks

## Context
SWE-SYNTH is being replaced by SWE-Infinite. You own this transition. Current SWE-SYNTH score: FAILED (Docker image missing on v2.2). Competitors score 31-47 on SWE-SYNTH — large opportunity.

## Phase 1: Understand the System (FIRST LOOP)

1. **Read all design docs**:
   - `repos/affine-swe-infinite/docs/en/01-HIGH-LEVEL-DESIGN.md`
   - `repos/affine-swe-infinite/docs/en/02-LOW-LEVEL-DESIGN.md`
   - `repos/affine-swe-infinite/docs/en/03-IMPLEMENTATION-GUIDE.md`
2. **Read eval format**:
   - `repos/affinetes/environments/swe_synth/config.yaml` (system prompts)
   - `repos/affinetes/environments/swe_synth/env.py` (scoring logic)
   - `knowledge/environments/SWE-INFINITE.md` (accumulated knowledge)
3. **Understand the pipeline code**:
   - `repos/affine-swe-infinite/src/orchestrator/pipeline.py`
   - `repos/affine-swe-infinite/src/models.py`
   - `repos/affine-swe-infinite/src/augmenters/codex_augmenter.py`

## Phase 2: Get Pipeline Running

1. **Check prerequisites**: Docker, GitHub token, AWS credentials (for DDB dedup)
2. **Test with single PR**: `docker compose run pipeline --single-pr pallets/flask <recent_pr>`
3. **Verify output**: Generated task JSON has correct fields
4. **Report**: Pipeline status, any blockers, first task example

## Phase 3: Generate Tasks + Collect Trajectories

1. **Run pipeline**: Process top Python repos, target 50-100 validated tasks
2. **Run fixer agent** (using GPT-5.4 or codex): collect successful fix conversations
3. **Format for training**: Convert trajectories to chat template (THOUGHT + bash format)
4. **Quality gate**: Only keep score=1.0, clear reasoning, minimal fixes
5. **Report**: Task count, trajectory success rate, data quality metrics

## Key Constraints
- Training data format: THOUGHT + bash (NOT tool_calls, NOT think tags)
- All entries must end with assistant turn
- seq=16384 for training — keep trajectories within this limit if possible
- Upload to HF after quality validation

## Timeline
- Phase 1: This loop (understand system)
- Phase 2: Next 2-3 loops (get pipeline working)
- Phase 3: Ongoing (generate tasks + trajectories continuously)

## References
- Experiment: `experiments/v2.4-navworld-gpt5.yaml` (v2.4 includes unchanged SWE-SYNTH 983, but future versions will use your data)
- Knowledge: `knowledge/environments/SWE-INFINITE.md`
