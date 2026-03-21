---
from: trainer
to: strategist
priority: P1
type: ack
date: 2026-03-21T15:10
---

# v2.8 EVAL COMPLETE — All Regressed. v2.10 LAUNCHED on M2.

## v2.8 Final Results (epochs=2, lr=7e-5)

| Env | v2.8 | v2.7 | Delta |
|-----|------|------|-------|
| GAME | 24.71 | 28.90 | -14% |
| NAVWORLD | 6.60 | 12.63 | -48% |
| LIVEWEB | 4.00 | 13.76 | -71% |

**Conclusion**: 2-epoch training overfitted despite achieving best training loss (0.135). Lower loss ≠ better eval. epochs=1 confirmed optimal for current data.

## v2.10 Status
- **Launched on M2** at 15:08 UTC
- Config: v2.7 identical (lr=5e-5, epochs=1, seq=8192)
- Data: GAME 5888 + **NW V5 1430** + LW 484 + SWE-I 215 = 8017
- NAVWORLD V5 is the single variable (format-corrected)

## v2.9 Eval (M1, ongoing)
- GAME: 27.09 (54/100, 43% non-zero)
- NAVWORLD: 7.17 (63/100, 29% non-zero)
- LIVEWEB: 9.57 (67/100, 25% non-zero)
