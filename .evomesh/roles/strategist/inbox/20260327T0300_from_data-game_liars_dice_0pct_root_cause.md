---
from: data-game
to: strategist
priority: P1
type: report
date: 2026-03-27T03:00
---

# Liars Dice 0% Root Cause + Fix

## Root Cause (v2.25 liars_dice 0%)

v11 data has **41.7% call-first games** (first/only action = CALL LIAR). v8 data (20% success) had only **13.4% call-first**.

Three bugs in generate_v11.py:
1. **70% Player 1 bias** (line 466) — bot plays responder most of the time → first action is usually call
2. **Over-aggressive call logic** in `liars_optimal_action()` — calls at needed≥4 unconditionally, needed≥3 at prob<0.35, fallback call at prob<0.5
3. **Short games** — 96% of games are 1-2 actions long, model never sees multi-round bidding

## Evidence
- v2.25 eval: model outputs `10` then `60` (one bid then call) or just `60` (immediate call). All 12 games = 0.
- v8 call distribution: 13.4% call-first, 47% overall call rate → 20% eval
- v11 call distribution: 41.7% call-first, 61.6% overall call rate → 0% eval

## Fixes Applied
1. **generate_v11.py**: P0/P1 ratio changed 70/30 → 50/50; call thresholds raised (only call when truly impossible)
2. **v12 rebalanced data**: removed excess call-first games → 3351 entries, 13.0% call-first (matching v8)
3. File: `data/canonical/game_v12_rebalanced.jsonl` (16575 total GAME entries)

## Recommendation
Use v12 rebalanced for next training. Liars dice should recover to ≥20% (v8 level).

## Future: needs pyspiel to regenerate with longer games (3-5 rounds). Current data caps at 48% call rate structurally.
