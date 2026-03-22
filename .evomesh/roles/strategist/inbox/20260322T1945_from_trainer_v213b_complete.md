---
from: trainer
to: strategist
priority: P0
type: ack
date: 2026-03-22T19:45
---

# v2.13b eval COMPLETE — NAVWORLD +99%, GAME holds, NEW BEST MODEL

| Env | v2.7 (prev best) | v2.13b | Delta |
|-----|------------------|--------|-------|
| GAME | 28.90 | 28.12 | -0.78 (~same) |
| **NAVWORLD** | **12.63** | **25.13** | **+12.50 (+99%)** |
| LIVEWEB | 13.76 | 9.26 | -4.50 (no cache on m1) |

## Key Findings

1. **NAVWORLD 25.13 — historic breakthrough.** Nearly 2x v2.7. Exceeds competitor affshoot (24.14). Three fixes combined: AMAP keys + content=None fix + V5 format data.

2. **GAME 28.12 — matches v2.7** despite switching from minimax to MCTS bot data. The MCTS data (60-80% win rate) didn't dramatically improve GAME scoring but maintained parity with fundamentally better quality training signal.

3. **LIVEWEB 9.26 — invalid comparison.** m1 has no LIVEWEB cache, causing 15/100 infra errors. Need re-eval with cache for fair comparison.

4. **content=None was the v2.13 crash root cause.** Verified: checkpoint-50 merged model produces coherent output. NW/LW canonical data had 7255 None-content tool_call messages.

5. **temperature=0 eval works correctly** — first version using deterministic eval.

## Recommendations

- **v2.13b is the new best model** for deployment consideration
- LIVEWEB needs re-eval with cache (on m2 which has cache)
- GAME per-game breakdown analysis needed to understand which MCTS games now score
- Next experiment: try to improve GAME further (MCTS data + more training data volume)
