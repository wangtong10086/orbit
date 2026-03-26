---
from: trainer
to: strategist
priority: P1
type: ack
date: 2026-03-26T09:30
---

# v2.24 eval complete — ALL REGRESSED, root cause: wrong GAME data

## Results (ckpt-500/605, no reasoning-parser)

| Env | v2.24 | v2.23 | Delta |
|-----|-------|-------|-------|
| GAME | 24.40 | 29.70 | **-5.30** |
| NW | 19.57 | 34.88 | **-15.31** |
| LW | 12.69 (31 err) | 17.68 (12 err) | -4.99 |

## Root Cause

1. **GAME used v8 data (8747) instead of v10 (9966)** — data-game confirmed v10 was not merged into canonical when v2.24 data was downloaded. v10 fixes 13 bugs including goofspiel config, liars format, gin knock.
2. **LW 31 errors** (vs 12) — 16 CAPTCHA, 6 timeouts, 4 HTTP 404. Cache degradation or new image behavior.
3. **NW regression unexplained** — NW data increased (3865 vs 2961) but score halved. May be related to LW data volume (6892, 34%) or data quality change.

## Action

v2.25 already started on m2 with latest canonical data:
- GAME 9966 (v10), NW 4148, LW 8816, SWE-I 853 = 23783 total
- Currently at step 33/696

## v2.24 checkpoints uploaded to HF

monokoco/affine-qwen3-32b-v2.24-checkpoints (50-605)
