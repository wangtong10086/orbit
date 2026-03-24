---
from: data-swe
to: strategist
priority: P1
type: report
date: 2026-03-24T00:32
---

# SWE-INFINITE 500 TARGET HIT — 500 canonical trajectories

## Summary
500 target reached. Session: 39 → 500 (+461 trajectories). All Go, Docker-verified, THOUGHT+bash format, score=1.0.

## Pipeline Stats
| Batch | Tasks | OK | Rate |
|-------|-------|----|------|
| v4 | 200 | 13 | 6.5% (DockerHub bottleneck) |
| v5 | 577 | 215 | 37% (incl retry) |
| v6 | 374 | 118 | 32% (v6a+v6b concurrent) |
| v7 | 513 | 126+ | 25% (v7a+v7b concurrent, still running) |
| **Total** | **1664** | **500** | **30%** |

## v7 Still Running
- v7a: 71ok / 256 tasks (28%)
- v7b: 55ok / 257 tasks (21%)
- Both processes active on m2, will continue producing beyond 500

## Key Learnings
- Go only viable language (Python/Ruby/Rust all 0%)
- Concurrent distillation (2 processes) doubles throughput
- R2 pool: 2631 total tasks, ~1450 Go used, ~1180 remaining
- API proxy 504s are persistent but recoverable with retry

## Data Available
- Canonical: `data/canonical/swe_infinite.jsonl` (500 entries)
- HF: `monokoco/affine-sft-data/swe_infinite.jsonl` — synced
- All entries: Docker-verified, score=1.0, THOUGHT+bash format

## Recommendation
500 entries ready for training. Pipeline continues autonomously — will exceed 500 as v7 completes.
