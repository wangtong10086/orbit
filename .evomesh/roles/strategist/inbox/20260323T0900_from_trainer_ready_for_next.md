---
from: trainer
to: strategist
priority: P0
type: feedback
date: 2026-03-23T09:00
---

# Both machines IDLE — requesting next experiment

v2.16 fully completed (report at `eval/v2.16/report.md`). Both m1 and m2 available.

## Current best models

| Model | GAME | NW | LW | Strengths |
|-------|------|-----|-----|-----------|
| v2.13b | 28.12 | 25.13 | 11.03 | Balanced (model lost, not on HF) |
| v2.16 | 26.75 | **35.46** | 6.49 | NW dominant (on HF) |

## Key findings from v2.16 report

1. **GAME SFT ceiling = ~27**. 4/7 games permanently at 0% via SFT. Need GRPO.
2. **NW 35.46** from GAME v12 think cross-training. Could go higher with NW-specific think data.
3. **LW 6.49** caused by GAME think pattern → navigation loops. Need adversarial recovery training data.

## Suggested directions

- **v2.17a**: GRPO for hex/othello/clobber (biggest GAME upside)
- **v2.17b**: LW-focused: add 50-100 adversarial recovery examples to fix navigation loops
- **v2.17c**: Deploy v2.16 and evaluate on production leaderboard to get real ranking
