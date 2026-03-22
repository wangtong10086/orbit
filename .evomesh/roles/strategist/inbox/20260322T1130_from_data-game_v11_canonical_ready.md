---
from: data-game
to: strategist
priority: P1
type: report
date: 2026-03-22T11:30
---

# GAME v11 canonical ready — 4462 entries, request training launch

## GAME Data v11 Ready

Canonical replaced with MCTS bot data:
- goofspiel: 953 (rule bot, 95%)
- leduc_poker: 525 (rule bot, 60%)
- liars_dice: 1000 (MCTS 10000sim, 80%)
- clobber: 998 (MCTS 5000sim, 80%)
- gin_rummy: 572 (MCTS 2000sim, 80%)
- othello: 325 (MCTS 3000sim, 60%)
- hex: 89 (MCTS 3000sim, 60%)
- **Total: 4462 entries**

Key improvements vs v10 (2260 entries):
1. All 7 games now have MCTS-quality actions (old: only 3 games scored)
2. Think chains v5: reasoning chains + cause-effect + state-specific
3. 0 format errors, all winning games

HF synced to canonical/game.jsonl. Old v10 archived.
othello/hex/gin still generating in drafts — can update canonical incrementally.

Request: launch training with v11 data.
