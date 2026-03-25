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

## v8 Data — Eval-Aligned Prompt, Full 9088 (2026-03-25)

**Training system prompt aligned to eval format** ("You must respond with ONLY the action ID. Do NOT include descriptions."), while assistant responses retain `<think>` blocks. Model must learn to think despite being told not to.

| Game | N | % | Turns | MCTS | Rule | AvgThkWords |
|------|---|---|-------|------|------|-------------|
| goofspiel | 1048 | 12% | 11440 | 0 | 11440 | 48 |
| leduc_poker | 1069 | 12% | 2336 | 0 | 2336 | 66 |
| gin_rummy | 1026 | 11% | 20385 | 17881 | 2504 | 45 |
| liars_dice | 1829 | 20% | 5041 | 1294 | 3747 | 58 |
| hex | 1211 | 13% | 23878 | 8980 | 14898 | 73 |
| othello | 1358 | 15% | 41274 | 40436 | 838 | 61 |
| clobber | 1547 | 17% | 17687 | 16140 | 1547 | 52 |

**Eval deployment**: sglang must use `--reasoning-parser qwen3` to enable thinking mode.
**Eval code**: `strip_think_tags=True` handles `<think>` in content automatically.

### v7 lesson learned
v7 reduced liars_dice from 1829→1000 entries. This caused regression (28.2%→24.9%). **Never reduce data count.**

## v2.20 Eval Results (2026-03-24, 100/100)

| Game | v2.17a | v2.17b | v2.20 | Change |
|------|--------|--------|-------|--------|
| goofspiel | 86.7% | 86.7% | 86.7% | stable |
| leduc_poker | 52.5% | 52.5% | 54.7% | stable |
| gin_rummy | 36.8% | 45.6% | **53.9%** | **+8% MCTS actions work** |
| liars_dice | 13.3% | 20.0% | **0.0%** | **regression (bid/call imbalance)** |
| hex | 0% | 0% | 0% | 0% think → unknown SFT ceiling |
| othello | 0% | 0% | 0% | 0% think → unknown SFT ceiling |
| clobber | 0% | 0% | 0% | 0% think → unknown SFT ceiling |

**Key findings**:
1. MCTS stats think improves gin_rummy (non-spatial, clear state)
2. Spatial games (hex/othello/clobber) confirmed SFT-unlearnable — 4x data made no difference
3. **Model still does NOT think** — 0% think rate across all games (same as v2.17a/b)
4. liars_dice regression root cause: more data (1829 vs ~500) taught model to "keep bidding" instead of "call liar at right time". v2.17a won by quick call_liar(60) on turn 2; v2.20 always bids instead.
5. Training data: call_liar=34.9% of actions, bid=65.1%. Model over-learned the dominant bid pattern.
6. Overall score 28.2% (v2.17b 29.7%) — gin_rummy +8% offset by liars_dice -20%

## Tools

| File | Purpose |
|------|---------|
| `scripts/game/mcts_helper.py` | Shared MCTS bot factory (configurable sim count) |
| `scripts/game/{game}_bot.py` | Per-game MCTS bot + rule-based think generator |
| `scripts/game/generate_fast.py` | Data generation: bot vs random |
| `scripts/game/test3.py` | Bot testing: bot vs MCTS (eval conditions) |
| `scripts/game/test_bots.sh` | Upload/test/status/analyze wrapper |
