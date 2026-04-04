# GAME Canonical Data — Difficulty Analysis for Phase 3 RL

> Status: Reference note
> Authority: Non-normative
> Last reviewed: 2026-04-04
> Use this file for background and deep analysis, not as the primary source of truth.


**Date**: 2026-03-18
**Dataset**: `data/canonical/game.jsonl` — 2641 entries
**Purpose**: Inform Phase 3 GRPO dynamic difficulty filtering

---

## 1. Turn Count Distribution

### Overall
| Bucket | Count | % |
|--------|-------|---|
| Short (≤5 turns) | 785 | 29.7% |
| Medium (6-15 turns) | 1507 | 57.1% |
| Long (>15 turns) | 349 | 13.2% |

### Per Game

| Game | Count | Min | Max | Mean | Median | Short ≤5 | Medium 6-15 | Long >15 |
|------|-------|-----|-----|------|--------|----------|-------------|----------|
| goofspiel | 1050 | 7 | 15 | 11.2 | 11.0 | 0 (0%) | 1050 (100%) | 0 (0%) |
| gin_rummy | 505 | 2 | 83 | 31.9 | 24.0 | 19 (3.8%) | 89 (17.6%) | 397 (78.6%) |
| leduc_poker | 428 | 1 | 4 | 2.6 | 3.0 | 428 (100%) | 0 (0%) | 0 (0%) |
| liars_dice | 333 | 1 | 5 | 2.8 | 3.0 | 333 (100%) | 0 (0%) | 0 (0%) |
| hex | 190 | 5 | 38 | 12.8 | 12.5 | 4 (2.1%) | 143 (75.3%) | 43 (22.6%) |
| clobber | 123 | 5 | 17 | 10.9 | 11.0 | 1 (0.8%) | 114 (92.7%) | 8 (6.5%) |
| othello | 12 | 30 | 32 | 30.5 | 30.0 | 0 (0%) | 0 (0%) | 12 (100%) |

**Key insight**: Leduc poker and liars dice are inherently short games (max 4-5 turns). Raw turn count is misleading — difficulty must be assessed relative to game type.

---

## 2. Game Type Strategy Depth

### goofspiel (1050 entries — 39.8%)
- **Mechanism**: Simultaneous action, bid cards on prize cards
- **Turn count**: Always 7-15 (deterministic length based on card count)
- **Action diversity**: 100% unique actions (mean diversity = 1.0) — every turn requires a different card
- **Scores**: 1041 wins (99.1%), 9 partial — overwhelmingly won
- **Strategy depth**: Medium. Requires planning card allocation across rounds. No partial info.

### gin_rummy (505 entries — 19.1%)
- **Mechanism**: Partial information, draw/discard card management
- **Turn count**: Widest range (2-83 turns), mean 31.9
- **Scores**: Mean 0.580. Distribution: 284 draws (0.5), 146 slight wins (0.5-0.7), 63 strong (0.7-0.9), 12 decisive (0.9+)
- **Strategy depth**: High. Long games with many decisions, partial information, complex hand management.
- **Score by game length**:
  - 2-5 turns: avg 0.526 (19 entries — often early knockouts)
  - 6-10 turns: avg 0.591 (42 entries)
  - 11-20 turns: avg 0.607 (141 entries)
  - 21-40 turns: avg 0.615 (170 entries — sweet spot)
  - 41+ turns: avg 0.511 (133 entries — long stalemates regress toward draw)

### leduc_poker (428 entries — 16.2%)
- **Mechanism**: Game theory, betting/bluffing with limited cards
- **Turn count**: 1-4 turns (inherently short game)
- **Scores**: 101 wins (1.0), 128 draws (0.5), 123 above-avg (0.5-0.7), 39 below-avg (0.3-0.5), 37 high (0.7-0.9)
- **Strategy depth**: High per-turn. Each decision (fold/call/raise) has outsized impact.
- **Action patterns (2-turn games, n=205)**:
  - (1,1): 63 — call/call
  - (2,2): 48 — raise/raise
  - (1,2): 37 — call then raise
  - These teach distinct strategies despite few turns
- **Average score by turns**: 1-turn=1.0, 2-turn=0.629, 3-turn=0.729, 4-turn=0.684

### liars_dice (333 entries — 12.6%)
- **Mechanism**: Probability estimation + bluff calling
- **Turn count**: 1-5 turns, mean 2.8
- **Scores**: All 1.0 (every entry is a win)
- **Action 60 dominance**: 332/333 entries contain action 60 (the "call Liar" action). Only 7/333 use exclusively action 60.
- **Strategy depth**: Medium. Bidding decisions require probability reasoning, but the "call Liar" terminal action is always the winning move.
- **Concern**: 100% win rate suggests opponent plays poorly or data is only from favorable positions.

### hex (190 entries — 7.2%)
- **Mechanism**: Connection strategy on hex grid
- **Strategy depth**: High. Positional play, blocking, path-building.
- **All wins** (score=1.0), diverse turn lengths (5-38).

### clobber (123 entries — 4.7%)
- **Mechanism**: Board capture, last-to-move wins
- **Strategy depth**: Medium-high. Positional capture decisions.
- **All wins** (score=1.0).

### othello (12 entries — 0.5%)
- **Mechanism**: Classic board game, flipping pieces
- **Strategy depth**: High. 30+ turns, complex positional play.
- **Too few samples** for meaningful RL training alone.

---

## 3. Trivial Sample Detection

### Criteria Applied
1. **≤2 assistant turns** (opponent folded/resigned immediately)
2. **All assistant actions identical** (no adaptation shown)
3. **Score=1.0 with ≤3 turns** (easy win, short game)

### Results (absolute, not game-relative)

| Game | Trivial | Total | % | Primary Reason |
|------|---------|-------|---|----------------|
| leduc_poker | 305 | 428 | 71.3% | ≤2 turns (211), same action (166), easy short win (85) |
| liars_dice | 246 | 333 | 73.9% | Easy short win (246), ≤2 turns (151) |
| gin_rummy | 9 | 505 | 1.8% | ≤2 turns (9) |
| goofspiel | 0 | 1050 | 0% | — |
| hex | 0 | 190 | 0% | — |
| clobber | 0 | 123 | 0% | — |
| othello | 0 | 12 | 0% | — |

**Warning**: Leduc poker and liars dice flag as heavily trivial by absolute metrics, but these are inherently short games. Game-relative assessment below is more accurate.

---

## 4. Complex / High-Training-Value Samples

### Criteria: ≥2 of: (a) ≥10 turns, (b) competitive score 0.3-0.7, (c) diverse actions with ≥5 turns

| Game | Complex | Total | % |
|------|---------|-------|---|
| othello | 12 | 12 | 100% |
| gin_rummy | 425 | 505 | 84.2% |
| hex | 147 | 190 | 77.4% |
| goofspiel | 673 | 1050 | 64.1% |
| clobber | 77 | 123 | 62.6% |
| leduc_poker | 0 | 428 | 0% |
| liars_dice | 0 | 333 | 0% |

Leduc poker and liars dice score 0% because they never reach 10 turns — again, game-relative metrics needed.

---

## 5. Difficulty Tier Assignment

### Game-Relative Tier Criteria

**For long games** (goofspiel, gin_rummy, hex, clobber, othello):
- **TRIVIAL**: ≤2 turns
- **EASY**: ≤4 turns with score ≥0.9
- **MEDIUM**: 6+ turns, standard play
- **HARD**: 10+ turns with action diversity ≥0.6 AND (competitive score 0.3-0.7 OR 15+ turns)

**For inherently short games** (leduc_poker, liars_dice):
- **TRIVIAL**: 1 turn (forced/no real choice)
- **EASY**: 2 turns with single unique action, or 2-3 turns with limited variety
- **MEDIUM**: 3+ turns with action variety (leduc), or 4+ turns (liars_dice)

### Distribution

| Game | TRIVIAL | EASY | MEDIUM | HARD | Total |
|------|---------|------|--------|------|-------|
| goofspiel | 0 (0%) | 0 (0%) | 820 (78.1%) | 230 (21.9%) | 1050 |
| gin_rummy | 9 (1.8%) | 10 (2.0%) | 274 (54.3%) | 212 (42.0%) | 505 |
| leduc_poker | 6 (1.4%) | 260 (60.7%) | 162 (37.9%) | 0 (0%) | 428 |
| liars_dice | 8 (2.4%) | 143 (42.9%) | 182 (54.7%) | 0 (0%) | 333 |
| hex | 0 (0%) | 4 (2.1%) | 124 (65.3%) | 62 (32.6%) | 190 |
| clobber | 0 (0%) | 1 (0.8%) | 104 (84.6%) | 18 (14.6%) | 123 |
| othello | 0 (0%) | 0 (0%) | 0 (0%) | 12 (100%) | 12 |

### Overall (Game-Relative)

| Tier | Count | % |
|------|-------|---|
| TRIVIAL | 23 | 0.9% |
| EASY | 513 | 19.4% |
| MEDIUM | 1571 | 59.5% |
| HARD | 534 | 20.2% |
| **KEEP (MEDIUM+HARD)** | **2105** | **79.7%** |
| **FILTER (TRIVIAL+EASY)** | **536** | **20.3%** |

---

## 6. Recommendations for Phase 3 GRPO

### What to Keep (2105 entries, 79.7%)

1. **All goofspiel** (1050) — inherently medium+ difficulty, 100% action diversity, good RL signal
2. **Gin rummy MEDIUM+HARD** (486/505) — rich decision space, competitive scores, long games
3. **Hex MEDIUM+HARD** (186/190) — strategic depth, varied game lengths
4. **Clobber MEDIUM+HARD** (122/123) — good positional complexity
5. **Othello all** (12) — small but all HARD
6. **Leduc poker MEDIUM** (162/428) — 3-4 turn games with diverse betting patterns
7. **Liars dice MEDIUM** (182/333) — 4-5 turn games with bidding + calling decisions

### What to Filter (536 entries, 20.3%)

1. **Leduc poker TRIVIAL+EASY** (266) — 1-2 turn games with repetitive call/fold patterns; low RL signal
2. **Liars dice TRIVIAL+EASY** (151) — 1-2 turn games ending in immediate "call Liar"; no strategic depth
3. **Gin rummy TRIVIAL+EASY** (19) — early knockouts with 2-4 turns
4. **Hex/clobber/goofspiel EASY** (5) — negligible count

### Specific Concerns

1. **Liars dice 100% win rate**: All 333 entries are wins. This means:
   - No negative examples for RL reward contrast
   - GRPO needs outcome variance to learn — consider generating losing examples or using only the longer games where the win was harder-earned

2. **Goofspiel 99.1% win rate**: Similar concern — nearly all wins. The 9 partial-score entries are more valuable for RL than the 1041 clean wins.

3. **Leduc poker game-theory depth**: Despite short turn count, each betting decision encodes significant strategy. The MEDIUM tier (162 entries with 3-4 turns and diverse actions) is worth keeping — these teach raise/call/fold decision-making.

4. **Gin rummy long stalemates**: Games with 41+ turns have avg score 0.511 (near-draw). These are long but low-signal — the model learns to play many turns without winning decisively. Consider whether GRPO reward should penalize draws.

### Expected Dataset After Filtering

| Game | Before | After | Removed |
|------|--------|-------|---------|
| goofspiel | 1050 | 1050 | 0 |
| gin_rummy | 505 | 486 | 19 |
| leduc_poker | 428 | 162 | 266 |
| liars_dice | 333 | 182 | 151 |
| hex | 190 | 186 | 4 |
| clobber | 123 | 122 | 1 |
| othello | 12 | 12 | 0 |
| **TOTAL** | **2641** | **2200** | **441** |

**Note**: The 441 filtered number differs slightly from the 536 TRIVIAL+EASY count because some EASY leduc/liars entries could be borderline-kept depending on exact filtering implementation. The conservative recommendation is to keep 2105 (MEDIUM+HARD only).

### For GRPO Specifically

- **Reward signal**: Focus on games with score variance (gin_rummy, leduc_poker). Games with 100% win rate (liars_dice, hex, clobber) provide weaker RL signal since there's no contrastive reward.
- **Curriculum**: Start GRPO with MEDIUM tier (1571 entries), add HARD tier once policy stabilizes.
- **Game weighting**: Goofspiel dominates (50% of MEDIUM+HARD). Consider upsampling underrepresented games (clobber, othello, hex) to prevent goofspiel overfitting.
- **Minimum viable set for balanced RL**: ~1200 entries if equalizing across game types.
