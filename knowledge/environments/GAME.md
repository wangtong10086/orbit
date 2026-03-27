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

## v10 Data — FINAL (2026-03-26)

### 13 Bugs Fixed (v8→v10)
1. Think chains: MCTS stats → IF-THEN rule-based
2. System prompt: aligned with eval rules exactly
3. goofspiel: points_order descending → random
4. goofspiel: state format → "Player 0: X points"
5. goofspiel: silent fallback bug (agents dependency, ALL v9 data was garbage)
6. liars_dice: numdice 1-5 → fixed 5
7. liars_dice: state format → structured (eval format)
8. gin_rummy: hand_size/knock_card → [7-9]/[8-10]
9. clobber: board → [5,6,7]² square
10. gin_rummy: knock override (76% knock rate, was 0%)
11. liars_dice: hand-aware bid + call-liar override (58% call rate)
12. Multi-difficulty opponent mix (random/weak/medium MCTS)
13. gen_sim restored (bot stronger than opponent)

### v10 Distribution (9466 total)

| Game | Entries | Action% | Random | Weak | Medium | v2.23 | Predicted |
|------|---------|---------|--------|------|--------|-------|-----------|
| goofspiel | 1200 | 11.9% | 1200 | — | — | 86.7% | 90% |
| leduc_poker | 1327 | 2.4% | 400 | 350 | 350 | 55.2% | 57% |
| liars_dice | 3039 | 5.5% | 1080 | 880 | 797 | 20.0% | 35% |
| gin_rummy | 500 | 17.2% | 400 | 200 | 100 | 42.6% | 55% |
| hex | 1200 | 22.8% | 600 | 258 | 300 | 0% | 3% |
| othello | 1000 | 27.1% | 600 | 300 | 300 | 0% | 5% |
| clobber | 1200 | 13.0% | 518 | 275 | 275 | 0% | 8% |

**Predicted GAME score: 36.1** (from 29.2)

File: `data/canonical/game_v10.jsonl`
Quality: 0 format errors across 110k+ actions. All quality gates passed.

**0 format errors across 169,245 actions.**
File: `data/v9/game_v9_final.jsonl` (8750 entries, shuffled)

**Training mix**: GAME 8750 + NW 3865 + LW 6892 + SWE-I 804 = 20311, NW = 19.0% ✓

### Per-Game Generation Rules

#### goofspiel (1000 entries)
- Keep best 1000 from current v8 data
- Rule v4 bot vs random (already 95% win rate)
- No changes needed — already high quality

#### leduc_poker (1000 entries)
- Regenerate with raise-aggressive bot variant
- When paired with board card: ALWAYS raise (not just call)
- When holding J (worst card): fold more often against raise
- Think chain: "My hand X paired with board Y → strong → RAISE"

#### gin_rummy (1500 entries) — CRITICAL FIX
- **Problem**: Model draws stock endlessly, never knocks
- **Fix**: Bot must check knock eligibility EVERY turn
- **Rule**: If deadwood ≤ knock_card threshold → KNOCK immediately
- **Data gate**: ≥30% of entries must include at least one knock action (action 55)
- **Think**: "Deadwood X ≤ threshold Y → KNOCK NOW. Waiting risks opponent improving."
- Generate vs MCTS 500sim to ensure realistic game states

#### liars_dice (1800 entries) — CRITICAL FIX
- **Problem**: Model memorized "5-5" opening bid regardless of actual hand
- **Root cause**: Training data opening bids not diverse enough
- **Fix rules**:
  1. Opening bid MUST be based on strongest face in hand
  2. Never bid quantity > (my support + 2) on opening
  3. Example: hand [1,2,3,4,5] → open 2-1 or 2-2 (not 5-5)
  4. Example: hand [3,3,3,6,6] → open 4-3 (3 threes + 1 wild = 4 support)
- **Call timing**: Include more "borderline call" situations (P=30-50%)
- **Think diversity**: Each opening must reference actual dice values
- Generate with MCTS 10000sim for decision quality

#### hex (2000 entries) — MASSIVE EXPANSION
- **Problem**: Only 612 entries, model plays horizontal lines (no path building)
- **Root cause**: Insufficient data + model doesn't learn diagonal/vertical connection
- **Fix rules**:
  1. Generate ALL data vs MCTS eval-level opponent (1000sim/50roll)
  2. Board sizes: 50% small (5x5, 7x7), 50% large (9x9, 11x11)
  3. Think chains MUST reference bridge patterns and path direction
  4. NEVER describe moves as "extending along row X" — always "connecting toward [top/bottom/left/right] edge"
  5. Every think must state: "My goal: connect [top-bottom / left-right]"
  6. Emphasize bridge concept: "Stones A and B share 2 empty neighbors → virtual connection → unbreakable"
  7. Win games only — bot must beat eval-level MCTS to generate data
- **Quality gate**: Each entry's think blocks reference at least one of: bridge, path cost, edge distance

#### othello (1500 entries) — CORNER-FIRST REGENERATION
- **Problem**: 2000 entries produced 0% — model ignores corners, no positional awareness
- **Root cause**: Think chains reference corners but model doesn't learn to prioritize them
- **Fix rules**:
  1. Think chain rule 1 (MANDATORY): "Corners available: [list]. → TAKE CORNER (never flips)"
  2. If no corner: "X-square check: [a2/b1/...] → AVOID (gives opponent corner)"
  3. Every think must start with corner/edge status scan
  4. Simplified think format: "SCAN: corners [a1:empty, h1:ours, a8:opp, h8:empty] → Rule: TAKE h8"
  5. Generate vs MCTS 1000sim/20roll
  6. Reduce think verbosity — focus on 2-3 rules per move, not all 9
- **Quality gate**: Every think starts with corner status scan

#### clobber (1200 entries) — MOBILITY FOCUS
- **Problem**: Model captures greedily, runs out of moves, always loses
- **Root cause**: Data doesn't teach "preserve own mobility" concept
- **Fix rules**:
  1. Think chain MUST report: "My moves: X, Opponent moves: Y"
  2. Prefer moves that maintain own mobility over maximum capture
  3. Endgame (≤12 pieces): think must include parity analysis
  4. "Safe capture" = capture where no adjacent opponent can recapture
  5. Think format: "Mobility: I have X captures, opp has Y. After this move: I'll have A, opp B. Favorable."
  6. Generate vs MCTS 1500sim/100roll
- **Quality gate**: Every think includes own/opp mobility count

### Generation Priority Order
1. **liars_dice** — highest ROI (20→50% = +30 points/7 = +4.3 GAME score)
2. **gin_rummy** — second highest ROI (42→62% = +2.8 GAME score)
3. **hex** — biggest volume gap (612→2000, potential +3.1 GAME score)
4. **othello** — quality regeneration (potential +2.9 GAME score)
5. **clobber** — quality regeneration (potential +2.1 GAME score)
6. **leduc_poker** — moderate improvement
7. **goofspiel** — maintain

### v8 Reference Data

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

### Lessons Learned (do NOT repeat)
- v7: reduced liars_dice 1829→1000. Caused regression. **Never reduce total count without replacement.**
- v2.20: liars_dice 0% — bid/call imbalance (34.9% call vs 65.1% bid). Model over-learned bidding.
- v2.23: spatial games 0% with 4x data. Volume alone doesn't help — quality/format must change.
- v2.23: model does NOT generate think blocks (0% think rate). System prompt conflict needs resolution.
- Canonical has 64 "unknown" game entries — must clean these out in v9.
- **v2.25: liars_dice 0% — call-first rate 41.7% (v8 was 13.4%). Model learned "call immediately".** Root cause: generate_v11.py bot_player=1 at 70% + over-aggressive call logic. Fix: balanced P0/P1 + conservative call threshold. v12 rebalanced to 13% call-first.

## Tools

| File | Purpose |
|------|---------|
| `scripts/game/mcts_helper.py` | Shared MCTS bot factory (configurable sim count) |
| `scripts/game/{game}_bot.py` | Per-game MCTS bot + rule-based think generator |
| `scripts/game/generate_fast.py` | Data generation: bot vs random |
| `scripts/game/test3.py` | Bot testing: bot vs MCTS (eval conditions) |
| `scripts/game/test_bots.sh` | Upload/test/status/analyze wrapper |
