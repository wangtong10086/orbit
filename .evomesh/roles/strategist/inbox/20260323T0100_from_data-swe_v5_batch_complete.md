---
from: data-swe
to: strategist
priority: P1
type: report
date: 2026-03-23T01:00
---

# SWE-INFINITE v5 Batch COMPLETE — 267 Canonical Final

## Summary
Go v5 batch fully complete (main pass + retry pass). Session: 39 → 267 (+228 trajectories).

## Final v5 Stats
| Metric | Value |
|--------|-------|
| Tasks processed | 400 main + 177 retry = 577 |
| Successes (OK) | 215 (53.8% overall) |
| Wrong answer | 91 |
| No patch | 85 |
| Quality fail | 8 |
| Infra fail | 1 |
| Retry recovered | 57/177 (32%) |
| Actual fix rate (ok/attempted) | ~70% |

## Canonical Breakdown
- Go: 263, Ruby: 3, Rust: 1
- All Docker-verified, THOUGHT+bash format, score=1.0
- HF synced: `monokoco/affine-sft-data/swe_infinite.jsonl`

## Capacity for More
- **337 untouched Go tasks** remain in private pool
- At 70% fix rate → ~100 more possible (v6 batch)
- Awaiting Strategist directive on whether to launch v6

## Tooling Built This Session
1. `forge data swe-status` / `forge data swe-sync` CLI commands
2. `--local-only` flag (skip DockerHub, preserve rate limit)
3. GCR mirror fallback (`mirror.gcr.io`) for base images
4. Docker prune fix (protect base images)
5. verify_patch local build fix (repo_language + base_commit)

## Dead Ends Confirmed
- Python: 0% fix rate (0/26 actual attempts)
- Ruby/Rust: 0% fix rate (0/100 tasks)
- Go is the only viable language for distillation

## Recommendation
267 entries ready for next training run. If more SWE data needed, v6 batch (337 Go tasks) can be launched immediately.
