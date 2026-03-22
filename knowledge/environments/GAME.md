# GAME Environment

## Key Facts
- 7 active games, eval uses OpenSpiel + MCTS opponent (except goofspiel: simultaneous → random)
- `strip_think_tags=True` — think blocks fully removed before action parsing
- Scoring: geometric mean across environments, scheduling weight 3.0
- Config variants per game: board sizes, card counts, etc. (from `generate_game_params`)

## Active Games + Bot Win Rate (GPU verified, vs MCTS, 2026-03-22)

| idx | Game | Opp MCTS | Old (minimax) | MCTS Bot (10局) | Bot sim | Strategy |
|-----|------|---------|--------------|-----------------|---------|----------|
| 0 | **goofspiel** | random | **95%** | — | — | 比例出价 + 终局调整 |
| 1 | **liars_dice** | 3000,200r | 0% | **80% (8/10)** | 10000,50r | MCTS搜索 + 概率解释 |
| 2 | **leduc_poker** | 3000,200r | **60%** | — | — | 决策表 + fold J |
| 3 | **gin_rummy** | 500,10r | 50% | **80% (8/10)** | 2000,20r | MCTS搜索 + meld解释 |
| 4 | **othello** | 1000,20r | 20% | **60% (6/10)** | 3000,20r | MCTS搜索 + 位置解释 |
| 6 | **hex** | 1000,50r | 30% | **60% (6/10)** | 3000,50r | MCTS搜索 + BFS路径解释 |
| 7 | **clobber** | 1500,100r | 0% | **80% (8/10)** | 5000,20r | MCTS搜索 + parity解释 |

## Canonical: v11 — 4462 entries (MCTS bot data)
- Old v10 data (2260 entries, minimax) archived
- All 7 games now use MCTS bot: 60-80% win rate vs eval MCTS opponent
- Think chains: v5 with reasoning chains, cause-effect, state-specific

## Tools

| File | Purpose |
|------|---------|
| `scripts/game/mcts_helper.py` | Shared MCTS bot factory (configurable sim count) |
| `scripts/game/{game}_bot.py` | Per-game MCTS bot + think generator |
| `scripts/game/generate_fast.py` | Data generation: bot vs random |
| `scripts/game/test3.py` | Bot testing: bot vs MCTS (eval conditions) |
| `scripts/game/test_bots.sh` | Upload/test/status/analyze wrapper |
