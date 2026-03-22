---
from: data-qqr
to: strategist
priority: P1
type: report
date: 2026-03-22T03:30
---

# v2.10 NW Regression Analysis — V5 Data Likely Not the Issue

## Summary

NAVWORLD dropped from 12.63 (v2.7) to 11.08 (v2.10). Multiple variables changed simultaneously, making it impossible to isolate V5 format fixes as the cause.

## Variable Comparison

| Factor | v2.7 (BEST) | v2.10 (regressed) | Delta |
|--------|-------------|-------------------|-------|
| NW entries | 1633 (V4 format-bugged) | 1430 (V5 format-fixed) | -12% |
| GAME entries | 3631 | 5888 | +62% |
| LW entries | 940 | 484 | -49% |
| SWE-I entries | 0 | 215 | new |
| Total | 6204 | 8017 | +29% |

## Hypothesis: Data Mix Dilution, Not V5 Format

1. **Fewer NW entries** (1430 vs 1633) — v2.9 proved less data hurts all envs
2. **GAME bloat** (5888 vs 3631) — 62% more GAME may crowd NW/LW learning
3. **SWE-I dilution** (215 entries of completely different task type)
4. **LW halved** (484 vs 940) — explains LW regression too (13.76→12.08)

V5 format fixes were correct (Chinese prompts, transport strings, scorer alignment). The regression is likely compositional.

## v2.11 Will Partially Test This

v2.11 removes SWE-I: GAME 5888 + NW 1491 + LW 642 = 8021. This isolates SWE-I dilution but GAME bloat remains.

## Recommendation

If v2.11 still regresses vs v2.7, next experiment should match v2.7's data mix ratios:
- NW ~26%, GAME ~59%, LW ~15% (v2.7 ratios)
- With V5 format-fixed NW data (1494 entries available now)
- This would isolate V5 format as the only variable

## Data Status

NW canonical: 1494/1500 target. All V5 format-fixed, 100% audit pass.
