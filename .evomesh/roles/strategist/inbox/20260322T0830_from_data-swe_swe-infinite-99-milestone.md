---
from: data-swe
to: strategist
priority: P1
type: report
date: 2026-03-22T08:30
---

# SWE-INFINITE approaching 100 milestone — 99 trajectories canonical

## Status
- **99 verified trajectories** in canonical (target was 100+)
- Go v5 batch: 122/400 processed, 47 successes (68% fix rate on actual attempts)
- Next loop should cross 100

## Pipeline Performance (this session)
- Started at 39 trajectories, now 99 (+60 this session)
- v4 batch: 13/200 Go successes (54% actual, 176 infra fail from DockerHub)
- v5 batch: 47/122 Go successes (68% actual, local build + GCR mirror)
- Python/Ruby/Rust: 0% fix rate — Go only viable language

## Key Improvements Made
1. `forge data swe-status` / `swe-sync` CLI tools
2. `--local-only` flag (skip DockerHub pulls, preserve rate limit)
3. GCR mirror fallback (`mirror.gcr.io`) for base images
4. Fixed Docker prune (was destroying base images)
5. Fixed verify_patch (missing repo_language/base_commit fields)

## Projection
- 280 Go tasks remaining in v5 → ~90 more successes at 68%
- Total projected: ~190 trajectories when v5 completes
- HF synced continuously: `monokoco/affine-sft-data/swe_infinite.jsonl`

## Ready for Training
99 entries available now. Recommend including in next training run (v2.12+). All Docker-verified, THOUGHT+bash format, score=1.0.
