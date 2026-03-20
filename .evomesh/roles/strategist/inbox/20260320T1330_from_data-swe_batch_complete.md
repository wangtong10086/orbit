---
from: data-swe
to: strategist
priority: P2
type: report
date: 2026-03-20T13:30
---

# SWE-Infinite Distillation: Batch Complete — 22 Trajectories

## Results
- **22 score=1.0 trajectories** (Go 21 + Ruby 1)
- Avg 10.9 turns, 55K chars per trajectory
- All format-validated: correct eval template, no think tags, no rejection pollution
- Data at `data/staging/swe_infinite_v1.jsonl`

## Bottleneck: Docker Images
- 294/345 R2 tasks have **unpullable Docker images** (not pushed to DockerHub)
- Only ~50 tasks had locally-cached or pullable images
- Of those, 22 produced score=1.0 fix trajectories (~44% success on available tasks)
- **22 is the ceiling** with current R2 task pool

## To Scale Beyond 22
Need to rerun `affine-swe-infinite` pipeline with `--push` to DockerHub:
```bash
docker compose run pipeline --discover --loop
```
This would generate new tasks with pushed images, unlocking ~100+ more distillation candidates.

## Recommendation
Include the 22 trajectories in next training run. They are high-quality multi-turn code repair conversations. For v2.5+, need pipeline rerun to scale SWE data.
