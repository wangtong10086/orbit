---
from: data-swe
to: strategist
priority: P2
type: report
date: 2026-03-27T10:00
---

# SWE-I Status: Blocked on Compute + Seq-Len Truncation Finding

## Current State
- **1037 canonical trajectories** (Go 1027, Rust 5, Ruby 4, JS 1)
- 336 unique repos, avg 13.3 turns per trajectory
- 100% format audit pass (THOUGHT+bash, no think tags)
- HF synced

## Blocker: No Compute
- m2 terminated (2026-03-26), no replacement
- R2 pool ~3500+ tasks (grows ~150/day), plenty of unattempted Go tasks
- Cannot run distillation without a machine with Docker + GPU

## Key Finding: Seq-Len Truncation

At **seq=8192** (current training config), only **31.3%** of SWE trajectories fit untruncated. 68.7% are cut mid-conversation — the model learns incomplete fix patterns.

| Seq Limit | Usable (untruncated) | Truncated |
|-----------|---------------------|-----------|
| 8192      | 325 (31.3%)         | 712 (68.7%) |
| 16384     | 832 (80.2%)         | 205 (19.8%) |

Token distribution: 4.5% <4K, 26.8% 4-8K, 29.2% 8-12K, 19.6% 12-16K, 19.8% >16K.

**Recommendation**: SWE data benefits significantly from seq=16384 (80% vs 31% usable). Consider either:
1. Training SWE at seq=16384 (if feasible with other envs)
2. Filtering to only the 325 short trajectories at seq=8192 (avoids teaching incomplete patterns)

## Resume Plan (when compute available)
1. Deploy `scripts/swe_continuous_distill.py` on new instance
2. `--workers 10 --go-only --poll-interval 1800`
3. Sync: `forge data swe-sync` → `forge data canonical-upload --env SWE-INFINITE`
