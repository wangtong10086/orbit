# GAME Environment

## Key Facts
- 7 active games, eval uses OpenSpiel + MCTS opponent (except goofspiel: simultaneous → random)
- `strip_think_tags=True` — think blocks stripped before action parsing, but model should still think
- Scoring: normalized from game utility range to [0,1]
- Config variants per game: board sizes (5/7/9/11 for hex), card counts, etc.
- System prompt instructs model to think in `<think>` tags then output action ID

## Active Games + Bot Strategy (2026-03-23)

| idx | Game | Opp MCTS | Bot | Win Rate | Strategy |
|-----|------|---------|-----|----------|----------|
| 0 | goofspiel | random | Rule v4 | 95% | 比例出价+终局调整 |
| 1 | liars_dice | 3000sim/200r | MCTS 10000sim | 80% | 固定决策框架: hand→概率→decision |
| 2 | leduc_poker | 3000sim/200r | Rule v4 | 60% | 决策表+pot odds+对手range |
| 3 | gin_rummy | 500sim/10r | MCTS 2000sim | 80% | deadwood/meld/knock timing |
| 4 | othello | 1000sim/20r | MCTS 3000sim | 67% | 9条规则(corner/chain/X-sq/mobility/compact/parity) |
| 6 | hex | 1000sim/50r | MCTS 3000sim | 60% | bridge/double threat/chain/ladder/acute corner |
| 7 | clobber | 1500sim/100r | MCTS 5000sim | 80% | safe capture/fragment/chain/mobility/parity |

## Think Chain Design Principles

All thinks use **IF-THEN rule patterns** that SFT can learn:
- `Rule: TAKE CORNER. a1 is available → corners never flip → take it`
- `Rule: SAFE CAPTURE. No adjacent opponent → can't be recaptured → safe`
- `Step 1: hand analysis → Step 2: probability → Step 3: decision`

NOT vague descriptions like "this is a good move because search says so."

## Canonical: v12 — system prompt fix
- System prompt changed from "respond with ONLY action ID" to "think in `<think>` tags then action ID"
- Eval uses `strip_think_tags=True` so safe — think auto-stripped
- Without this fix, model skips thinking and outputs bare numbers (confirmed by v2.13b eval)

## v2.20 Eval Results (2026-03-24, 76/100)

| Game | v2.17a | v2.17b | v2.20 | Change |
|------|--------|--------|-------|--------|
| goofspiel | 86.7% | 86.7% | 83.3% | stable |
| leduc_poker | 52.5% | 52.5% | 54.1% | stable |
| gin_rummy | 36.8% | 45.6% | **54.8%** | **+9% MCTS think works** |
| liars_dice | 13.3% | 20.0% | **0.0%** | **regression** |
| hex | 0% | 0% | 0% | SFT ceiling confirmed |
| othello | 0% | 0% | 0% | SFT ceiling confirmed |
| clobber | 0% | 0% | 0% | SFT ceiling confirmed |

**Key findings**:
1. MCTS stats think improves gin_rummy (non-spatial, clear state) but regresses liars_dice
2. Spatial games (hex/othello/clobber) confirmed SFT-unlearnable — 4x data made no difference
3. liars_dice regression likely caused by long think (avg 303 chars) interfering with action selection
4. Overall score unchanged (~29%) — gin_rummy gains offset by liars_dice loss

## Tools

| File | Purpose |
|------|---------|
| `scripts/game/mcts_helper.py` | Shared MCTS bot factory (configurable sim count) |
| `scripts/game/{game}_bot.py` | Per-game MCTS bot + rule-based think generator |
| `scripts/game/generate_fast.py` | Data generation: bot vs random |
| `scripts/game/test3.py` | Bot testing: bot vs MCTS (eval conditions) |
| `scripts/game/test_bots.sh` | Upload/test/status/analyze wrapper |
