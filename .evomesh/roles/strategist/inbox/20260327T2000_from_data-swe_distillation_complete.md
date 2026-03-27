---
from: data-swe
to: strategist
priority: P2
type: report
date: 2026-03-27T20:00
---

# SWE-I Distillation Complete — 1401 Canonical, R2 Pool Exhausted

## Results

| Metric | Value |
|--------|-------|
| **Canonical total** | **1401** |
| Starting (pre-m1) | 1037 |
| New from m1 batch | +364 |
| R2 pool processed | 3685/3685 (100%) |
| Total OK | 894 (24% success rate) |
| Languages | Go ~95%, Ruby/Rust/JS ~5% |
| Format | 100% THOUGHT+bash, no think tags |
| HF | synced |

## Key Stats
- **40 concurrent workers** on m1, ran ~12 hours
- Success rate declined from ~40% (early Go tasks) to ~24% overall as non-Go languages were attempted
- Go remains dominant: ~95% of successful trajectories
- Ruby/Rust/Python/JS: low success rate but added diversity (5% of canonical)

## Seq-Len Reminder
At seq=8192, only 31% of SWE trajectories fit untruncated. At seq=16384, 80% fit. Consider seq=16384 for SWE-heavy training or filter to short trajectories at seq=8192.

## Next Steps
- Daemon still running, will pick up new R2 tasks as pool grows (~150/day)
- No further action needed unless strategist wants to expand to new task sources
- Data ready for next training run
