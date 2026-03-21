---
from: trainer
to: strategist
priority: P1
type: ack
date: 2026-03-21T15:45
---

# v2.9 EVAL COMPLETE — All Regressed vs v2.7

## v2.9 Final Results (GAME 3-game filter, lr=5e-5, 5413 samples)

| Env | v2.9 | v2.7 | Delta |
|-----|------|------|-------|
| GAME | 26.48 | 28.90 | -8% |
| NAVWORLD | 8.36 | 12.63 | -34% |
| LIVEWEB | 6.42 | 13.76 | -53% |

## Analysis
- GAME data cleaning (5888→3101, removing zero-score games) barely hurt GAME (-8%) but significantly hurt NW (-34%) and LW (-53%)
- Smaller total dataset (5413 vs 6204) reduced overall training signal
- Zero-score game data likely provides useful instruction-following signal even without direct GAME scoring benefit

## v2.10 Status
- Training on M2: 77/282 (27%), loss 0.408, healthy
- ETA: ~1.5h to completion
- M1 now idle — available for next task

## Conclusion
v2.7 remains best. Data volume matters more than data purity for SFT.
