---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-22T08:32
---

# v2.12 APPROVED (CORRECTED) — Match v2.7 proportions. Launch on M2 NOW.

**SUPERSEDES** previous v2.12 directive (20260322T0817). Data mix was WRONG.

## Corrected Data Mix (from data-qqr analysis of v2.7)

v2.7 actual proportions: GAME 59%, NW 26%, LW 15%.

| Env | v2.7 (target) | v2.12 (plan) | Source |
|-----|--------------|-------------|--------|
| GAME | 3631 (59%) | **~3400** | Subsample from canonical 5888 |
| NAVWORLD | 1633 (26%) | **1494** (all V5) | Full V5 canonical |
| LIVEWEB | 940 (15%) | **690** (all) | Full canonical (690 available, use all) |
| SWE-I | 0 | **0** | Excluded |
| **Total** | **6204** | **~5584** | |

Note: LW canonical only has 690, so we can't reach v2.7's 940. Use all 690 (12.4% of mix vs v2.7's 15%). This is the closest we can get.

## CRITICAL: Verify v2.7 Data Before Launch

Please verify v2.7's actual data composition (data-qqr says GAME 3631, NW 1633, LW 940). Check the v2.7 training log or prepare-data output.

## Config

Same as v2.7: lr=5e-5, seq=8192, epochs=1, batch=2, grad_accum=2.

## Launch Steps

1. Prepare data with subsampling (GAME ~3400, NW all 1494, LW all 690, no SWE-I)
2. Launch training on M2
3. After training: merge → sglang → eval (3 envs × 100 samples)
