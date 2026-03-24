---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-24T17:00
---

# v2.21 APPROVED — Launch with latest canonical data

## Data
```bash
cat data/canonical/game.jsonl data/canonical/navworld.jsonl data/canonical/liveweb.jsonl data/canonical/swe_infinite.jsonl > combined.jsonl
# Expected: 14168 lines
```

| Env | Count |
|-----|-------|
| GAME | 9088 |
| NAVWORLD | 1768 |
| LIVEWEB | 2627 |
| SWE-I | 685 |
| **Total** | **14168** |

## Config (same)
lr=5e-5, seq=8192, epochs=1, batch=2, grad_accum=2, packing=true, DDP, save_steps=50

## MANDATORY Protocol
1. Kill LW eval (stuck at 89/100) + kill sglang before training
2. Pre-validation: `wc -l combined.jsonl` = 14168, content=None = 0
3. After training: merge from **last numbered checkpoint** (NOT final!)
4. Sanity test immediately
5. Eval all 4 envs: GAME + NW + LW + SWE-I (if SWE-I config ready)
6. Save eval results incrementally (per task)
7. Formal report + results.tsv update
