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
# Expected: 22148 lines
```

| Env | Count | % |
|-----|-------|---|
| GAME | 8623 | 38.9% |
| NW | 3865 | 17.5% |
| LW | 8816 | 39.8% |
| SWE-I | 844 | 3.8% |
| **Total** | **22148** | |

## Config
lr=5e-5, seq=8192, epochs=1, batch=2, grad_accum=2, packing=true, DDP, save_steps=100

## CRITICAL RULES
1. **NO --reasoning-parser qwen3** (confirmed harmful)
2. Merge from checkpoint **~80-85%** of total steps (NOT final)
3. Pre-validation: `wc -l combined.jsonl` = 22148, content=None = 0
4. Eval: GAME + NW + LW + SWE-I (4 envs, 100 samples, no reasoning-parser)
