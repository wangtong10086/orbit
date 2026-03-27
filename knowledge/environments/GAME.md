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

## v12 Data — CURRENT (2026-03-27, on HF)

**Strategy**: ~~NO think blocks~~ **WRONG — top miner confirmed to use `<think>` blocks (tested 2026-03-27).** Need to restore think blocks. `reasoning_tokens=0` but think is in content, stripped by `strip_think_tags=True` at eval.
**File**: `data/canonical/game.jsonl` → HF `monokoco/affine-sft-data`

### v12 GAME Distribution (16,575 total)

| Game | Entries | % | Avg Acts/Game | Key Stat | v2.25 Score |
|------|---------|---|---------------|----------|-------------|
| goofspiel | 2,000 | 12.1% | 11.1 | — | 83.3% |
| leduc_poker | 2,000 | 12.1% | 2.7 | 0% fold, 68% call, 32% raise | 48.4% |
| liars_dice | 3,351 | 20.2% | 1.9 | 13% call-first ✅ (was 41.7%) | 0% → expect 20%+ |
| gin_rummy | 604 | 3.6% | 23.8 | 55.8% games have knock (v8=95%) | 30.4% |
| hex | 2,106 | 12.7% | 9.3 | no think, 16% diversity (5x5) | 0% |
| othello | 1,321 | 8.0% | 30.2 | no think | 0% |
| clobber | 5,193 | 31.3% | 12.3 | no think | 0% |

### Full Training Mix (31,781 total)

| Env | Entries | % | Size |
|-----|---------|---|------|
| GAME | 16,575 | 52.2% | 112 MB |
| LIVEWEB | 9,999 | 31.5% | 610 MB |
| NAVWORLD | 4,170 | 13.1% | 116 MB |
| SWE-I | 1,037 | 3.3% | 50 MB |

### Known Data Issues (need pyspiel to fix)

1. **gin_rummy**: only 604 entries (v8 had 1026), only 55.8% games knock (v8=95%). Need more data + bot that knocks more.
2. **leduc_poker**: 0% fold actions. Bot never folds. Need fold examples for J vs raise.
3. **spatial games (hex/oth/clob)**: SFT ceiling at 0%. Need GRPO/DPO method switch.

### Regeneration Priority (need pyspiel)
1. **gin_rummy** — 604→1000+ entries, bot must knock 95%+ of games (v8 had 95%, v12 only 55.8%)
2. **leduc_poker** — add fold logic (J vs raise → fold). Currently 0% fold in data.
3. **spatial games** — SFT ceiling at 0%. Need GRPO/DPO, not more data.

### Lessons Learned (do NOT repeat)
- v7: reduced liars_dice 1829→1000. Caused regression. **Never reduce total count without replacement.**
- v2.20: liars_dice 0% — bid/call imbalance (34.9% call vs 65.1% bid). Model over-learned bidding.
- v2.23: spatial games 0% with 4x data. Volume alone doesn't help — quality/format must change.
- v2.23: model does NOT generate think blocks (0% think rate). System prompt conflict needs resolution.
- Canonical has 64 "unknown" game entries — must clean these out in v9.
- **v2.25: liars_dice 0% — call-first rate 41.7% (v8 was 13.4%). Model learned "call immediately".** Root cause: generate_v11.py bot_player=1 at 70% + over-aggressive call logic. Fix: balanced P0/P1 + conservative call threshold. v12 rebalanced to 13% call-first.
- **v2.25: gin_rummy knock rate 0% in eval** — training data has only 2.3% knock actions (55). Model never learns to knock. Need ≥10% knock rate in data.
- **v2.25: leduc_poker 0% fold in eval** — training data has 0% fold actions. Model became over-passive (78% call vs 22% raise). Need fold examples (~10%) to teach when to fold weak hands.
- **v2.25 eval had 20/100 infrastructure errors** (connection failures) counted as 0 score, inflating the GAME score penalty.

## Tools

| File | Purpose |
|------|---------|
| `scripts/game/mcts_helper.py` | Shared MCTS bot factory (configurable sim count) |
| `scripts/game/{game}_bot.py` | Per-game MCTS bot + rule-based think generator |
| `scripts/game/generate_fast.py` | Data generation: bot vs random |
| `scripts/game/test3.py` | Bot testing: bot vs MCTS (eval conditions) |
| `scripts/game/test_bots.sh` | Upload/test/status/analyze wrapper |
