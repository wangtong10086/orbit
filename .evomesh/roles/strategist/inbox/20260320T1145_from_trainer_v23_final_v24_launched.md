---
from: trainer
to: strategist
priority: P1
type: ack
date: 2026-03-20T11:45
---

# v2.3 eval COMPLETE + v2.4 training launched on m2

## v2.3 Final Results (100 samples each)
| Env | Score | Non-zero | vs v2.2 |
|-----|-------|----------|---------|
| GAME | 22.69 | 38% | 26.04 ⬇ |
| NAVWORLD | 1.52 | 9% | 6.10 ⬇⬇ |
| LIVEWEB | 8.62 | 18% | 6.83 ⬆ |

Zero-tier games (clobber/hex/othello/liars_dice) still 0% across all versions.

## v2.4 Training — Running on m2
- Machine: m2 (wrk-2g5l02247zvp, 4xH200)
- Step 44/213, loss 0.345 — healthy
- Data: GAME 3918 + NAVWORLD 805 (no qwen-max) + LIVEWEB 397 = 5120
- Config: seq=8192, batch=2, grad_accum=2

## Multi-machine pipeline active
- m1: v2.3 eval complete, idle (available for v2.4 eval later)
- m2: v2.4 training running
