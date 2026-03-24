---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-25T00:00
---

# v2.22 APPROVED — Launch with expanded NW data

## Data (ALL current canonical)
```bash
cat data/canonical/game.jsonl data/canonical/navworld.jsonl data/canonical/liveweb.jsonl data/canonical/swe_infinite.jsonl > combined.jsonl
# Expected: 15416 lines
```

| Env | Count | Change |
|-----|-------|--------|
| GAME | 9088 | v6 prompt restored |
| NW | 2966 | +68% (was 1768) |
| LW | 2627 | unchanged |
| SWE-I | 735 | +47 |
| **Total** | **15416** | |

## Config (same)
lr=5e-5, seq=8192, epochs=1, batch=2, grad_accum=2, packing=true, DDP, save_steps=50

## MANDATORY
1. Kill sglang before training
2. Pre-validation: `wc -l combined.jsonl` = 15416, content=None = 0
3. Merge from **numbered checkpoint** (NOT final!)
4. Sanity test immediately after merge
5. Eval 4 envs: GAME + NW + LW + SWE-I
6. Incremental eval saves
