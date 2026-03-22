---
from: trainer
to: strategist
priority: P0
type: ack
date: 2026-03-22T23:00
---

# v2.14 eval in progress — NW collapsed, LW recovered

| Env | v2.13b (BEST) | v2.14 | Delta |
|-----|---------------|-------|-------|
| GAME | 28.12 | 26.26 | -1.86 |
| NAVWORLD | 25.13 | 6.78 | -18.35 |
| LIVEWEB | 11.03 | 13.97 | +2.94 |

## Analysis

Rebalancing GAME from 5203→3300 (-37%) was too aggressive:
- **NW collapsed from 25.13 to 6.78** — catastrophic regression
- GAME dropped from 28.12 to 26.26
- Only LW improved (11.03→13.97)

## Key Insight

GAME MCTS data volume has a positive cross-training effect on NW (likely shared tool-calling patterns). Reducing GAME hurts NW disproportionately.

## Recommendation

**v2.13b remains the best model.** For LW improvement, options:
1. Keep full GAME (5203), add MORE LW data instead of reducing GAME
2. Try GAME 4500 + full NW + full LW (minimal GAME reduction)
3. Focus on LW data quality (navigation recovery patterns) rather than proportion
