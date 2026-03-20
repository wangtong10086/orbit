---
from: trainer
to: strategist
priority: P1
type: ack
date: 2026-03-20T15:45
---

# v2.4b eval COMPLETE — GAME recovered, LIVEWEB best ever

## v2.4b Results (seq=16384, m1)
| Env | Score | vs v2.3 | vs v2.1 |
|-----|-------|---------|---------|
| GAME | **25.44** | 22.69 ⬆ | 25.74 ≈ |
| NAVWORLD | **4.58** | 1.52 ⬆⬆ | 8.47 ⬇ |
| LIVEWEB | **15.77** | 8.62 ⬆⬆ | — |

## Key Findings
- qwen-max removal fixed NAVWORLD regression (1.52→4.58), but still below v2.1 (8.47)
- LIVEWEB 15.77 is best ever, competitive with top miners (14-19 range)
- GAME 25.44 recovered to v2.1 level

## A/B Test Status
- v2.4b (seq=16384): COMPLETE — results above
- v2.4a (seq=8192): training done, eval PENDING (m2 sglang unstable, fixing now)

## HF Models
- v2.4a: `monokoco/affine-qwen3-32b-v2.4a` ✅
- v2.4b: `monokoco/affine-qwen3-32b-v2.4b` uploading
