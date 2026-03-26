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

## v9 Data Strategy — Target GAME 50 (2026-03-26)

### v2.23 Per-Game Diagnosis (100 samples)

| Game | Score | Root Cause of Failure | Fix Required |
|------|-------|----------------------|--------------|
| goofspiel | 86.7% | Working well | Maintain |
| leduc_poker | 55.2% | Too passive, folds good hands | Raise-aggressive data |
| gin_rummy | 42.6% | **Never knocks** — draws 10+ cycles | Knock-when-eligible focus |
| liars_dice | 20.0% | **Memorized "5-5" opening** regardless of hand | Diverse hand-aware openings |
| hex | 0% | **Plays horizontal lines** — no path building | Diagonal/vertical path data |
| othello | 0% | **Ignores corners** — zero positional awareness | Corner-priority regeneration |
| clobber | 0% | **Captures greedily** — runs out of moves first | Mobility-preservation data |

### Target Scores

| Game | Current | Target | Gain | Method |
|------|---------|--------|------|--------|
| goofspiel | 86.7% | 92% | +5.3 | Quality audit only |
| leduc_poker | 55.2% | 70% | +14.8 | Raise-with-strong-hand data |
| gin_rummy | 42.6% | 62% | +19.4 | Knock-focused regeneration |
| liars_dice | 20.0% | 50% | +30.0 | Fix 5-5 bug, diverse data |
| hex | 0% | 22% | +22.0 | vs-MCTS, path-building focus |
| othello | 0% | 20% | +20.0 | Corner-first regeneration |
| clobber | 0% | 15% | +15.0 | Mobility-preservation |
| **Total** | **29.2** | **47.3** | **+18.1** | |

Optimistic path to 50: (95+72+65+52+25+22+18)/7 = **49.9**

### Data Distribution — v9 FINAL (8750 total, capped for NW 19%)

| Game | v8 Count | v9 Count | % | Quality Gate Result |
|------|----------|----------|---|---------------------|
| goofspiel | 1048 | 1000 | 11.4% | ✓ 45% bid strategy, 48 avg think words |
| leduc_poker | 1069 | 1000 | 11.4% | ✓ 100% pot odds, 29% fold decisions |
| gin_rummy | 1026 | 653 | 7.5% | ✓ 165 knocks (28.5%), 98% deadwood think |
| liars_dice | 804 | 1800 | 20.6% | ✓ 51% call liar, 94% Step framework |
| hex | 612 | 1637 | 18.7% | ✓ 100% goal prefix, 100% bridge patterns |
| othello | 2000 | 1500 | 17.1% | ✓ 100% corner scan, 70% rule-based |
| clobber | 2000 | 1160 | 13.3% | ✓ 100% rule-based, 53% mobility report |

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

## Tools

| File | Purpose |
|------|---------|
| `scripts/game/mcts_helper.py` | Shared MCTS bot factory (configurable sim count) |
| `scripts/game/{game}_bot.py` | Per-game MCTS bot + rule-based think generator |
| `scripts/game/generate_fast.py` | Data generation: bot vs random |
| `scripts/game/test3.py` | Bot testing: bot vs MCTS (eval conditions) |
| `scripts/game/test_bots.sh` | Upload/test/status/analyze wrapper |
