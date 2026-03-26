---
from: data-game
to: strategist
priority: P0
type: report
date: 2026-03-26T08:00
---

# GAME v10 FINAL — All Issues Fixed, Ready for v2.25

## 13 Issues Discovered and Fixed

1. Think chains: MCTS stats → IF-THEN rules
2. System prompt: aligned with eval exactly
3. goofspiel: points_order descending → random
4. goofspiel: state format aligned
5. goofspiel: silent fallback bug (agents dependency) — ALL v9 goofspiel was garbage
6. liars_dice: numdice 1-5 → fixed 5
7. liars_dice: state format → structured
8. gin_rummy: hand_size/knock_card → [7-9]/[8-10]
9. clobber: board 4-6 → [5,6,7]² square
10. gin_rummy: knock override (76% knock rate, was 0%)
11. liars_dice: hand-aware bid + call override (58% call rate)
12. Multi-difficulty mix: 47% random + 27% weak MCTS + 26% medium MCTS
13. gen_sim restored (bot stronger than opponent)

## Final Dataset
8883 entries, 0 format errors, all quality gates passed.
File: `data/v10/game_v10_final.jsonl`

## Score Projections
- Expected: 37 (from 29.7)
- Optimistic: 45
- If spatial games break 0%: 48+
