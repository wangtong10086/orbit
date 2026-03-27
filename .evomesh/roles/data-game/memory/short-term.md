# Short-term Memory

## Current State (2026-03-27 loop 24)
- Diagnosed liars_dice 0% regression in v2.25
- Root cause: 41.7% call-first games in v11 data (v8 had 13.4%)
- Fixed generate_v11.py: balanced P0/P1 + conservative call thresholds
- Created v12 rebalanced data: 16575 entries, liars 3351 (13% call-first)
- Sent P1 reports to Strategist + Data Agent

## v2.25 Liars Dice Analysis
- v11 data: 5000 liars entries, 61.6% call rate, 41.7% call-first
- v8 data (20% success): 804 liars entries, 47% call rate, 13.4% call-first
- Model behavior in v2.25 eval: outputs "10" then "60" or just "60" — always calls
- All 12 liars games scored 0

## Fixes Applied
1. generate_v11.py line 466: bot_player P1 ratio 70% → 50%
2. liars_optimal_action(): raised call thresholds (only call when truly impossible)
3. Rebalanced existing data: removed 1649 call-first games

## Files Created
- data/canonical/game_v12_rebalanced.jsonl (16575 entries)
- data/v11/liars_dice_v12_rebalanced.jsonl (3351 entries)

## Waiting For
- Data Agent: canonical merge of v12 rebalanced → HF upload
- Strategist: approval for next training with v12 data
- Environment with pyspiel: regenerate liars_dice with longer games (3-5 rounds)

## Next If Reactivated
- If pyspiel available: regenerate liars_dice with fixed bot (target 3+ round games)
- Analyze v2.25 eval for other game regressions (leduc -6.8, gin -6.2)
- Check if spatial games (hex/othello/clobber) show any improvement signals
