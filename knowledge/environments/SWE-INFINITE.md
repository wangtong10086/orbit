# SWE-Infinite Environment

## Overview

SWE-Infinite evaluates code repair ability on real GitHub PRs. Model interacts with a Docker container via multi-turn THOUGHT + bash commands. Binary scoring: 0 or 1.

## Evaluation Flow

1. Model receives problem_statement (bug description from PR)
2. Model runs bash commands in Docker container (/app)
3. Model sees real terminal output after each command
4. Model fixes code and submits: `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git add -A && git diff --cached`
5. Tests run. All FAIL_TO_PASS must pass → score=1.0

## Model Response Format

```
THOUGHT: [reasoning]

```bash
single_command_here
```
```

- Exactly ONE bash block per turn
- NO `<think>` tags
- Commands run in subshells (no persistent env/dir changes)

## Task Source

- **Private R2 pool**: `affine-swe-infinite-private` bucket (~2500 tasks, growing daily)
- Pipeline auto-discovers GitHub PRs → Docker build → test validation → R2
- Docker images on `affinefoundation/swe_infinite_images`
- Languages: Go (~56%), Ruby (~17%), Python (~13%), Rust (~9%), JS (~3%)

## Distillation Pipeline (current)

**Script**: `scripts/swe_distill.py`
**Method**: GPT-5.4 as agent in real Docker containers, verified by running tests

```
Private R2 task → docker pull image → GPT-5.4 agent loop (THOUGHT+bash)
→ extract patch → verify in fresh container → score=1.0 only → export JSONL
```

**Current config**:
- API: `api.aicodemirror.com` proxy (unstable — 520/504 errors)
- Retry: 15 attempts, 1800s timeout, 15-120s exponential backoff
- Auto re-queue: API-failed tasks retry at end of batch
- Auto Docker prune every 10 tasks

**Current run**: 1834 tasks pending on GPU (4xH200), 11 trajectories collected

## Key Learnings

1. **Only real Docker trajectories are usable** — synthetic (GPT-generated observations) teach wrong distribution
2. **API instability is #1 bottleneck** — proxy returns 520/504 on ~50% of calls. Mitigate with aggressive retry + long timeout
3. **Go easiest to fix** — most successes are Go projects
4. **Small patches succeed more** — patch ≤ 3K chars has higher fix rate
5. **Premature submit guard needed** — reject submit before step 3, strip from exported data

## Dead Ends (DO NOT REPEAT)

- **Synthetic trajectories**: GPT-5.4 generates fake observations (avg 11K chars vs real 36K). Teaches wrong distribution.
- **Think tags**: Conflicts with THOUGHT format
- **seq < 16384**: Most conversations truncated
- **Public R2 pool only**: Only ~50 of 345 had pullable Docker images. Private pool has 2500+ with images.
- **Short API timeout**: 30s/300s caused mass failures. Need 1800s.
- **3x retry**: Not enough for unstable proxy. Need 15x.
