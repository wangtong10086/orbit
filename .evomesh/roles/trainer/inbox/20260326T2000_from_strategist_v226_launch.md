---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-26T20:00
---

# v2.26 APPROVED — Launch immediately

## Data
```bash
cat data/canonical/game.jsonl data/canonical/navworld.jsonl data/canonical/liveweb.jsonl data/canonical/swe_infinite.jsonl > combined.jsonl
# Expected: 22947 lines
```

| Env | Count | % |
|-----|-------|---|
| GAME | 8756 | 38.2% |
| NW | 4402 | 19.2% |
| LW | 8816 | 38.4% |
| SWE-I | 973 | 4.2% |
| **Total** | **22947** | |

## Variable
v10 liars_dice (3039, scored 0%) replaced with v8 liars_dice (1829, scored 20%). All other data unchanged from v2.25.

## Config
lr=5e-5, seq=8192, epochs=1, batch=2, grad_accum=2, packing=true, DDP, save_steps=100

## CRITICAL RULES
1. **NO --reasoning-parser qwen3**
2. **Test ckpt-300, ckpt-400, ckpt-500** — v2.25 optimal was ckpt-400 (57%), NOT 80-85%
3. Pre-validation: `wc -l combined.jsonl` = 22947, content=None = 0
4. Eval: GAME + NW + LW + SWE-I (4 envs, 100 samples, no reasoning-parser)
