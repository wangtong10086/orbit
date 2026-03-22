---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-22T19:47
---

# v2.14 APPROVED — Rebalance GAME/LW proportions. Launch on M1 immediately.

## v2.13b FINAL RESULTS (NEW BEST GM)

| Env | v2.13b | v2.7 | Delta |
|-----|--------|------|-------|
| GAME | 28.14 | 28.90 | -2.6% |
| **NAVWORLD** | **25.13** | 12.63 | **+99%** |
| LIVEWEB | 7.79 | 13.76 | -43.4% (16 errors) |
| **GM** | **17.7** | 17.1 | **+3.5%** |

## v2.14 — Fix LW Regression

**Variable**: Reduce GAME from 65% to ~55% to recover LIVEWEB.

**Data mix** (subsample GAME):
- GAME: **~3300** (subsample from 4462 v11 MCTS canonical)
- NAVWORLD: **1636** (all V5 canonical)
- LIVEWEB: **754** (all canonical)
- SWE-I: **0**
- Total: **~5690**

**Config**: Same as v2.13b (lr=5e-5, seq=8192, epochs=1).

## Launch Steps

1. Prepare data with GAME subsampling (~3300 from 4462)
2. Launch training on M1
3. After training: merge → sglang → eval (3 envs × 100)
4. **CRITICAL**: Ensure AMAP keys are set. Save all eval files per ROLE rules.

**See**: `experiments/v2.14-draft.yaml`
