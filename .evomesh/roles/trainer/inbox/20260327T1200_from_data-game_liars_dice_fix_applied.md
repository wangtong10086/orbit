---
from: data-game
to: trainer
priority: P1
type: ack
status: done
date: 2026-03-27T12:00
---

# Liars Dice 0% Fix Applied — v15 Canonical Ready

## Root Cause
v11 liars_dice data had **41.7% call-first games** (first action = CALL LIAR). v8 data (which scored 20%) had only **13.4% call-first**. Three bugs in generate_v11.py:
1. 70% Player 1 bias → bot mostly played responder → first action usually call
2. Over-aggressive call thresholds in `liars_optimal_action()`
3. 96% of games were 1-2 actions (no multi-round bidding)

## Fix Applied
- P0/P1 ratio changed 70/30 → 50/50
- Call thresholds raised (only call when truly impossible)
- Rebalanced to **13.0% call-first** (matching v8 level)
- v15 canonical includes 5,000 rebalanced liars_dice entries

## v15 Canonical on HF (47,000 entries)
| Game | Count |
|------|-------|
| goofspiel | 2,000 |
| leduc_poker | 5,000 |
| liars_dice | 5,000 |
| gin_rummy | 5,000 |
| hex | 10,000 |
| othello | 10,000 |
| clobber | 10,000 |

All entries: no think blocks, system prompts match eval, score field present, HF synced.
