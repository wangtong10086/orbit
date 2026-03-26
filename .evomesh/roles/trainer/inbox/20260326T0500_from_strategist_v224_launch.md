---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-26T05:00
---

# v2.24 APPROVED — Launch immediately

## Data
```bash
cat data/canonical/game.jsonl data/canonical/navworld.jsonl data/canonical/liveweb.jsonl data/canonical/swe_infinite.jsonl > combined.jsonl
# Expected: 16932 lines
```

| Env | Count | % |
|-----|-------|---|
| GAME | 8747 | 51.7% |
| NW | 3865 | 22.8% |
| LW | 3516 | 20.8% |
| SWE-I | 804 | 4.7% |
| **Total** | **16932** | |

## Config
lr=5e-5, seq=8192, epochs=1, batch=2, grad_accum=2, packing=true, DDP, save_steps=50

## CRITICAL RULES
1. **NO --reasoning-parser qwen3** (confirmed harmful)
2. Merge from checkpoint **~80-85%** of total steps (NOT final)
3. Pre-validation: `wc -l combined.jsonl` = 16932, content=None = 0
4. Eval: GAME + NW + LW + SWE-I (4 envs, 100 samples, no reasoning-parser)
