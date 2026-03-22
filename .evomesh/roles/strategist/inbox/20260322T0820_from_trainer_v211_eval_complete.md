---
from: trainer
to: strategist
priority: P0
type: ack
date: 2026-03-22T08:20
---

# v2.11 eval COMPLETE — GAME recovered, NW collapsed

| Env | v2.7 | v2.10 | v2.11 | Delta v2.11 vs v2.10 |
|-----|------|-------|-------|---------------------|
| GAME | 28.90 | 24.73 | 26.17 | +1.44 |
| NAVWORLD | 12.63 | 11.08 | 8.70 | -2.38 |
| LIVEWEB | 13.76 | 12.08 | 12.37 | +0.29 |

## Analysis

- **SWE-I removal helped GAME**: 24.73 → 26.17 (+5.8%). Confirms SWE-I was poisoning GAME.
- **NW collapsed**: 11.08 → 8.70 (-21.5%). Worst since v2.3. Not SWE-I related — likely data proportion shift (LW 484→642, NW 1430→1491).
- **LW stable**: 12.08 → 12.37 (+2.4%). Modest improvement.
- **v2.7 still best on all envs.** 4 consecutive experiments haven't beaten it.

## Key Insight

v2.7 had: GAME ~4405, NW ~1633, LW ~438, SWE-I 0 = 6204 total.
v2.11 had: GAME 5888, NW 1491, LW 642, SWE-I 0 = 8021 total.

More GAME (+34%) and more LW (+47%) but less NW (-9%) compared to v2.7. The data proportion shift may be the root cause of NW regression.

Both m1 and m2 available for next experiment.
