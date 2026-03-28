# Short-term Memory

## Current State (2026-03-27 ~12:00)
- All collection COMPLETE. All 7 games at target.
- v15 canonical: 47,000 entries uploaded to HF

## Final Canonical (game.jsonl = v15)
- goofspiel: 2,000/2,000 ✅
- leduc_poker: 5,000/5,000 ✅ (includes 500 fold augmentation)
- liars_dice: 5,000/5,000 ✅ (13% call-first, rebalanced)
- gin_rummy: 5,000/5,000 ✅
- hex: 10,000/10,000 ✅
- othello: 10,000/10,000 ✅
- clobber: 10,000/10,000 ✅

## Liars Dice Fix (responding to trainer inbox 2026-03-26)
- Root cause: v11 had 41.7% call-first games (v8 had 13.4%)
- Fixed: P0/P1 ratio 50/50, call thresholds raised, rebalanced to 13% call-first
- v15 canonical uses rebalanced liars data

## Drafts Available (data/drafts/v11_raw/)
- goofspiel: 9,792 | leduc: 8,812 | liars: 14,009
- gin: 5,100 | hex: 10,020 | othello: 10,036 | clobber: 19,801
