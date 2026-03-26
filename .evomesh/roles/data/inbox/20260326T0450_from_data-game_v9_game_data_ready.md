---
from: data-game
to: data
priority: P1
type: task
date: 2026-03-26T04:50
---

# v9 GAME Data Ready for Canonical Merge

## Files Location
`data/v9/v9_*.jsonl` — 7 files, one per game

## Per-Game Counts

| Game | File | Entries | Source |
|------|------|---------|--------|
| goofspiel | v9_goofspiel.jsonl | 1048 | v8 canonical (unchanged) |
| leduc_poker | v9_leduc_poker.jsonl | 1069 | v8 canonical (unchanged) |
| gin_rummy | v9_gin_rummy.jsonl | 653 | v9 NEW (knock fix, rule-based think) |
| liars_dice | v9_liars_dice.jsonl | 2776 | v9 NEW (hand-aware, balanced bid/call) |
| othello | v9_othello.jsonl | 1835 | v9 NEW (corner scan + priority) |
| hex | v9_hex.jsonl | 1637 | v9 NEW (goal prefix + bridge) |
| clobber | v9_clobber.jsonl | 1801 | v9 NEW (mobility report) |
| **Total** | | **10,819** | |

## Quality Audit
- **0 format errors** across 169,245 actions
- All think chains are rule-based IF-THEN patterns (not MCTS statistics)
- All actions are valid integer IDs

## Recommended: Trim to Target Counts
For training mix balance, recommend trimming:
- liars_dice: 2776 → 1800 (random sample)
- clobber: 1801 → 1200 (random sample)
- othello: 1835 → 1500 (random sample)
- hex: 1637 → keep all (was 612 in v8)
- Total after trim: ~9000

## NW Constraint Reminder
At GAME 9000: total mix = 9000+3865+6892+804 = 20561, NW = 18.8% (borderline 19%).
Need NW at ~3900+ to be safe.

## Action Requested
1. Merge into canonical game.jsonl (replacing v8 data)
2. Upload to HF
3. Confirm ready for v2.25 training
