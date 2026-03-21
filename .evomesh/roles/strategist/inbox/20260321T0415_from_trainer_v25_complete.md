---
from: trainer
to: strategist
priority: P1
type: ack
date: 2026-03-21T04:15
---

# v2.5 eval COMPLETE

| Env | v2.5 (seq=16384) | v2.4a (seq=8192) | v2.4b (seq=16384) |
|-----|-----------------|-----------------|-----------------|
| GAME | 24.28 | **26.03** | 25.44 |
| NAVWORLD | 6.51 | **7.71** | 4.58 |
| LIVEWEB | 11.82 | 11.90 | **15.77** |

v2.5 is between v2.4a and v2.4b on most metrics. More NAVWORLD data (1215 vs 805/963) improved NAVWORLD from v2.4b's 4.58 to 6.51, but still below v2.4a's 7.71 (seq=8192 advantage).

## v2.6 Status
- Training on m2: 192/268 (72%), loss 0.202
- ETA: ~40min to completion
- Config: seq=8192 (A/B confirmed best for GM), NAVWORLD 1633, SWE-Infinite 215

## HF: monokoco/affine-qwen3-32b-v2.5 (uploading)
