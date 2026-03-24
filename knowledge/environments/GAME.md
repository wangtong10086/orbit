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

## v7 Data — System Prompt Alignment Fix (2026-03-24)

**Root cause of 0% think**: training system prompt said "think in `<think>` tags" but eval says "respond with ONLY the action ID. Do NOT include descriptions." Model follows eval instruction → never thinks.

**Fix**: replaced all 9088 training system prompts to match eval format exactly. Assistant responses still contain `<think>` blocks. Model learns to think even when told "only action ID". Eval `strip_think_tags=True` handles stripping.

**Data audit (v7)**:

| Game | N | AvgTurns | MCTS% | UniqueThink | Issue |
|------|---|----------|-------|-------------|-------|
| goofspiel | 1048 | 10.9 | 0% | 7986 | OK |
| leduc_poker | 1069 | 2.2 | 0% | 78 | Think diversity low |
| gin_rummy | 1026 | 19.9 | 88% | 14921 | OK |
| liars_dice | 1829 | 2.8 | 26% | 1609 | call_liar only 35% of actions |
| hex | 1211 | 19.7 | 38% | 12001 | OK |
| othello | 1358 | 30.4 | 98% | 40231 | OK |
| clobber | 1547 | 11.4 | 91% | 16141 | OK |

**Known remaining issues** (to fix after v7 training validates think alignment):
1. liars_dice: call_liar(60) underrepresented (35% vs 65% bid). May need resampling.
2. leduc_poker: only 78 unique think patterns. May need diversity boost.

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
