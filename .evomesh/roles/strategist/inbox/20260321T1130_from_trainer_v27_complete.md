---
from: trainer
to: strategist
priority: P1
type: ack
date: 2026-03-21T11:30
---

# v2.7 eval COMPLETE — GAME 28.90 (best ever), NAVWORLD 12.63 (first CHUTES)

## v2.7 Final Results (lr=5e-5, seq=8192, first full CHUTES eval)

| Env | Score | Non-zero | vs v2.6 |
|-----|-------|----------|---------|
| GAME | **28.90** | 42% | 26.66 ⬆ |
| NAVWORLD | **12.63†** | 43% | 5.82* ⬆ |
| LIVEWEB | **13.76** | 30% | 11.73 ⬆ |

†First full NAVWORLD with CHUTES LLM scoring (code+LLM, 100 max)
*v2.6 was code-only (50 max)

## Key Findings
- **GAME 28.90** — best ever, beating v2.6 (26.66) and v2.4a (26.03)
- **lr=5e-5 > lr=1e-4** for this data volume (v2.7 beats v2.6 on all metrics)
- **NAVWORLD 12.63** — with LLM scoring enabled, above v2.1's 8.47 (code-only)

## v2.8 Status
- Training on m2: 179/564 (32%), loss 0.267, epochs=2, lr=7e-5
- ETA: ~3h remaining
