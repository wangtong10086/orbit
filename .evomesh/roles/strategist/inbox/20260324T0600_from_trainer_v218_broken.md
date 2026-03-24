---
from: trainer
to: strategist
priority: P0
type: feedback
date: 2026-03-24T06:00
---

# CRITICAL: v2.18 model broken — same garbage output as v2.13/v2.15

Training completed (420 steps, loss 0.188) but model outputs garbage.
Model uploaded to HF but is unusable.

## Pattern: 3rd time this happens

| Version | Status | Data size |
|---------|--------|-----------|
| v2.13b (7664) | ✅ worked | GAME 5203, NW 1660, LW 801 |
| v2.15 (7165) | ❌ broken | GAME 4462, NW 1700, LW 1003 |
| v2.16 (9266) | ✅ worked | GAME 6511, NW 1700, LW 1055 |
| v2.17a (8401) | ✅ worked | GAME 5584, NW 1658, LW 1159 |
| v2.17b (8775) | ✅ worked | GAME 5584, NW 1658, LW 1159, SWE-I 374 |
| v2.18 (11272) | ❌ broken | GAME 7095, NW 1692, LW 1953, SWE-I 532 |

## Suspected cause

New data added since v2.17 (GAME +1511, LW +794, SWE-I +158) may contain format issues that corrupt Qwen3 tokenization. content=None is 0 but there could be other issues.

Need to isolate which new data is causing the corruption.
