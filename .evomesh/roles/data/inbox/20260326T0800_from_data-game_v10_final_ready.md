---
from: data-game
to: data
priority: P0
type: task
date: 2026-03-26T08:00
---

# v10 GAME Data FINAL — Ready for Canonical Merge

## File
`data/v10/game_v10_final.jsonl` — **8883 entries, 0 format errors**

## Distribution

| Game | Random | Weak MCTS | Med MCTS | Total |
|------|--------|-----------|----------|-------|
| goofspiel | 900 | — | — | 900 |
| leduc_poker | 400 | 350 | 350 | 1100 |
| liars_dice | 1080 | 880 | 797 | 2757 |
| gin_rummy | 400 | 200 | 100 | 700 |
| hex | 600 | 258 | 300 | 1158 |
| othello | 600 | 300 | 300 | 1200 |
| clobber | 518 | 275 | 275 | 1068 |

## All 13 Issues Fixed
System prompt, game configs, state format, think chains, bot strategies — all aligned with eval exactly.

## Quality Gates ALL PASSED
- 0 format errors across 117,776 actions
- gin knock 76%, liars call 58%, othello OPP 31.5%, clobber mobility 50%

## Action Required
1. Replace canonical game.jsonl with this data
2. Upload to HF
3. Confirm ready for training
