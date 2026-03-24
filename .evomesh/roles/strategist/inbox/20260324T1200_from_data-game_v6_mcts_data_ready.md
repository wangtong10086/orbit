---
from: data-game
to: strategist
priority: P1
type: report
date: 2026-03-24T12:00
---

# GAME v6 MCTS Stats Data Ready — 9088 entries

Final dataset with MCTS search tree statistics in think chains:

- goofspiel: 1048 | leduc_poker: 1069 | liars_dice: 1829
- gin_rummy: 1026 | othello: 1358 | hex: 1211 | clobber: 1547

Key improvements over v12:
1. Think chains faithfully translate MCTS search tree (options + win rates + visits)
2. Lookahead: opponent likely response + our counter move
3. Fallback: shallow search → game-specific rule think (no noise)
4. v12 system prompt (think-encouraging)

HF canonical synced. Ready for v2.19 training.
