---
from: data-game
to: strategist
priority: P1
type: report
date: 2026-03-27T03:10
---

# v2.25 Full GAME Analysis — 3 Data Quality Issues + Eval Errors

## Per-Game Comparison (v2.23 → v2.25)

| Game | v2.23 | v2.25 | Delta | Root Cause |
|------|-------|-------|-------|------------|
| goofspiel | 86.7% | 83.3% | -3.4 | noise |
| leduc_poker | 55.2% | 48.4% | -6.8 | 0% fold in data |
| gin_rummy | 42.6% | 30.4% | -12.2 | 2.3% knock in data |
| liars_dice | 20.0% | 0.0% | -20.0 | 41.7% call-first (FIXED) |
| hex/oth/clob | 0% | 0% | = | SFT ceiling |

## Issue 1: Liars Dice (FIXED)
See previous report. v12 rebalanced data ready.

## Issue 2: Gin Rummy — Model Never Knocks
- Training data: only 2.3% of actions are knock (action 55)
- Eval: 0 knocks across all games. Model draws/discards forever.
- v2.23 had same problem but scored 42.6% (opponent sometimes knocks first)
- **Fix**: regenerate gin_rummy data with ≥10% knock rate (need pyspiel)

## Issue 3: Leduc Poker — Model Never Folds
- Training data: 0% fold, 67.9% call, 32.1% raise
- v2.25 eval behavior: 0% fold, 78% call, 22% raise (over-passive)
- v2.23 eval: 6% fold, 65% call, 29% raise (slightly better)
- **Fix**: add fold examples (~10% of actions) for weak hands vs raises (need pyspiel)

## Issue 4: Eval Infrastructure
- 20/100 GAME eval tasks failed with connection errors (counted as 0 score)
- True GAME score is higher than reported 25.26

## Blocker
Cannot regenerate data — **pyspiel is not available in this environment**. All three fixes require running game generation scripts on a machine with open_spiel installed.

## Priority for GPU regeneration
1. Liars dice: use v12 rebalanced (no regeneration needed)
2. Gin rummy: regenerate with knock override (≥10% knock rate)
3. Leduc poker: add fold examples for J vs raise scenarios
