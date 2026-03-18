# GAME v3 Bot Data — Quality Analysis for Rejection Sampling

**Date**: 2026-03-18
**Files analyzed**:
- `data/game_v3_bot_goofspiel.jsonl` (192 entries)
- `data/game_v3_bot_gin_rummy.jsonl` (440 entries)
- `data/game_v3_bot_leduc_poker.jsonl` (58 entries)

**Existing baseline**: `data/v1_mixed.jsonl` (273 goofspiel, 430 gin_rummy, 47 leduc_poker)

---

## Executive Summary

| Metric | Goofspiel | Gin Rummy | Leduc Poker |
|--------|-----------|-----------|-------------|
| Entries | 192 | 440 | 58 |
| Win rate | 99.0% | 1.8% | 67.2% |
| Unique action sequences | 100% | 100% | 17.2% |
| Unique think contents | 161 | **1** | 10 |
| Think quality | Templated but varied | **BROKEN — single template** | Formulaic but functional |
| Recommended keep rate | ~79% | **0% (regenerate)** | ~69% |

**Verdict**: Goofspiel is usable after filtering. Gin rummy is fundamentally broken. Leduc poker is marginal — small volume, zero folds, narrow strategy.

---

## 1. Goofspiel (192 entries)

### Strategy Diversity

- **100% unique action sequences** — every game plays out differently due to different prize card orderings.
- Deck sizes vary: N=8 (44), N=10 (31), N=12 (39), N=14 (42), N=16 (36) — good coverage.

**Bid-to-prize matching pattern (dominant strategy: bid == prize)**:
- 67.0% of all bids exactly match the prize value.
- Per-entry match rate: mean=69.4%, median=71.4%.
- Distribution of per-entry match rates:
  - 100% match: 32 entries (16.7%)
  - 75-100%: 42 entries
  - 50-75%: 80 entries
  - 25-50%: 37 entries
  - 0-25%: 1 entry

**Concern**: The "bid == prize" strategy is overwhelmingly dominant. This teaches the model a single heuristic (match your bid to the prize value), with only minor deviations. High-value prizes (9+) almost always get high bids; low-value prizes (1-3) almost always get low bids. Standard deviations are small (0.6-1.2) across all prize values.

**Bid pattern by prize value** (showing limited strategic variation):
- Prize 1: avg bid 1.3 (std 0.9)
- Prize 6: avg bid 5.8 (std 1.1)
- Prize 12: avg bid 12.0 (std 0.8)
- Prize 16: avg bid 16.0 (std 0.0) — zero variation

### Thinking Quality

- 161 unique think strings across 2102 total think tags (7.7% unique).
- Top think templates are formulaic: "Prize card worth X points, [low/high] value. [Bid low/Bid X to compete aggressively]."
- All thinks are >30 chars and reference game state — better than gin_rummy.
- However, the reasoning is shallow: it classifies prizes as "low/medium/high" then applies a fixed rule. No opponent modeling, no resource planning across rounds.

### Game State Complexity

- Turns: min=7, max=15, avg=10.9, median=11.0.
- Distribution by deck size (N/2+1 to N turns per game): {7: 44, 9: 31, 11: 39, 13: 42, 15: 36}.
- No "trivial" short games — minimum 7 turns.

### Score Analysis

- 190/192 entries score 1.0 (99.0%), 2 entries score 0.5.
- **All wins, near-zero variance**. The bot strategy crushes the opponent consistently.
- Score-turns correlation: 0.142 (weak positive — longer games still win).

### Complementarity with Existing Data

- **0 overlapping action sequences** with v1 data — all 192 are truly new patterns.
- Think overlap: 119/161 new thinks already exist in v1 (74%).
- v1 avg turns: 11.2, v3 avg turns: 10.9 — nearly identical complexity.
- New data adds volume but not strategic diversity beyond what v1 already has.

### Quality Tiering

| Tier | Count | % | Criteria |
|------|-------|---|----------|
| HIGH | 117 | 60.9% | >=10 turns, >=3 unique thinks per entry |
| MEDIUM | 33 | 17.2% | Standard games |
| LOW | 42 | 21.9% | <=6 turns or trivially short |

**Recommendation**: Keep HIGH + MEDIUM (150 entries, 78.1%). The LOW tier entries are short games (N=8 deck) with <7 turns that provide minimal learning signal.

---

## 2. Gin Rummy (440 entries) — CRITICAL PROBLEMS

### Strategy Diversity

- **100% unique action sequences** (due to different card deals), but this is misleading.
- Draw decisions: 49.2% upcard, 50.8% stock — nearly random.
- FirstUpcard: 161 draw, 178 pass — also near-random.

### CRITICAL ISSUE: Single Think Template

**Every single one of 26,708 think tags across all 440 entries contains the identical text:**
> "Organize hand, keep cards that form melds, discard highest deadwood."

This is **catastrophic for training quality**. The model learns that this single template is the correct reasoning for every gin rummy decision, regardless of:
- Hand composition
- Game phase
- Deadwood count
- Opponent's revealed discards
- Whether to draw upcard vs stock

The existing v1 data has the **exact same problem** (3,043 thinks, all identical). Adding v3 data would double down on this broken pattern.

### Win Rate: Near-Zero

- **Wins: 8 (1.8%), Draws: 432 (98.2%), Losses: 0**.
- Score 0.5 = draw/timeout. The bot almost never actually wins.
- Deadwood progression shows the bot often fails to reduce deadwood effectively:
  - Example: 73 turns, deadwood 41→46 (went UP), min reached 7 but couldn't close.
  - Example: 27 turns, deadwood 54→56, min 33.
  - Example: 81 turns, deadwood 54→58, min 26.

### Discard Analysis

Card discard distribution is nearly uniform across all cards — the bot is not making strategic discard decisions. Top 20 discarded cards range from 257-277 occurrences each, showing no preference for discarding high-deadwood cards.

### Game Length

- Turns: min=2, max=86, avg=60.7, median=64.0.
- 403/440 (91.6%) entries have 31+ turns — extremely long games.
- Only 31 entries reach knock phase, only 4 achieve gin (0 deadwood).
- The bot plays very long games without being able to close out.

### Complementarity

- 1 overlapping sequence with v1 data (nearly zero overlap in actions).
- v1 avg turns: 20.6, v3 avg turns: 60.7 — v3 games are 3x longer.
- v1 avg score: 0.608, v3 avg score: 0.509 — v3 performs worse.
- v3 adds more losing games with identical broken reasoning.

### Quality Tiering

| Tier | Count | % |
|------|-------|---|
| HIGH | 0 | 0.0% |
| MEDIUM | 437 | 99.3% |
| LOW | 3 | 0.7% |

Note: zero entries qualify as HIGH because the single-template thinking means no entry has >=3 unique thinks.

**Recommendation**: **REJECT ALL 440 entries.** This data would teach the model to:
1. Use a single generic reasoning template for all gin rummy decisions
2. Play 60+ turn games that end in draws
3. Make near-random draw/discard decisions

The gin rummy data needs complete regeneration with:
- Game-state-aware thinking (referencing specific cards, melds, deadwood)
- A bot strategy that can actually win (current win rate: 1.8%)
- Shorter, decisive games

---

## 3. Leduc Poker (58 entries)

### Strategy Diversity

- **Only 10 unique action sequences** across 58 entries (17.2% unique).
- Top patterns: `1-1` (call-call, 16x), `2-2` (raise-raise, 14x), `1-2` (call-raise, 6x).
- **Zero folds in 58 entries.** The bot never folds, even with J (weakest card).
- Action distribution: 54.2% call, 45.8% raise, 0% fold.

### Card-Dependent Strategy (Simplistic but Correct Direction)

| Card | Count | Raise Rate | Fold Rate |
|------|-------|------------|-----------|
| K | 28 | 100% | 0% |
| Q | 18 | 17% | 0% |
| J | 12 | 58% | 0% |

- K always raises — reasonable.
- Q mostly calls — reasonable.
- J raises 58% of the time and **never folds** — problematic. Real poker requires folding weak hands against raises.

### Thinking Quality

- 10 unique thinks across 144 total (6.9% unique).
- Top think covers 32.6% of all decisions.
- Thinks are formulaic but reference the specific card held.
- Templates: "I have [K/Q/J], [strategy]" or "[card] + public card = pair, raise."

### Game Complexity

- Very short games: min=2, max=4, avg=2.5, median=2.0.
- This is inherent to Leduc poker (only 2 betting rounds).
- 36 entries with 2 turns, 16 with 3, 6 with 4.

### Situation Coverage

Good spread across card combinations:
- K+Q(no-pair): 10, K+K(PAIR): 9, K+J(no-pair): 9
- Q+K(no-pair): 8, Q+J(no-pair): 7, Q+Q(PAIR): 3
- J+J(PAIR): 7, J+K(no-pair): 3, J+Q(no-pair): 2

Missing: some situations have very few examples (J+Q: only 2).

### Score Analysis

- 39 wins (67.2%), 19 draws (32.8%), 0 losses.
- Mean score: 0.836.
- No correlation between game length and score (r=0.009).

### Complementarity

- **9/10 new action patterns already exist in v1 data** — only 1 truly new pattern.
- Think overlap: 9/10 new thinks already in v1.
- V3 is almost entirely duplicating existing patterns, adding volume not diversity.

### Quality Tiering

| Tier | Count | % | Criteria |
|------|-------|---|----------|
| HIGH | 18 | 31.0% | >=3 turns, >=2 unique thinks, includes raises |
| MEDIUM | 40 | 69.0% | Standard 2-turn games |
| LOW | 0 | 0.0% | — |

**Recommendation**: Keep HIGH tier only (18 entries). MEDIUM entries duplicate existing patterns. The zero-fold problem means even HIGH entries teach an incomplete strategy.

---

## Overall Recommendations for Rejection Sampling

### Keep (168 entries total)
- **Goofspiel HIGH+MEDIUM**: 150 entries (78.1% of 192)
- **Leduc HIGH**: 18 entries (31.0% of 58)

### Reject (522 entries)
- **Goofspiel LOW**: 42 entries (short trivial games)
- **Gin Rummy ALL**: 440 entries (broken thinking, near-zero win rate)
- **Leduc MEDIUM**: 40 entries (duplicate patterns)

### Systemic Issues to Fix Before Regeneration

1. **Gin rummy thinking is completely broken** — needs game-state-aware reasoning, not a single template. This is the same problem as v1 data, so it's a generation pipeline issue.

2. **Gin rummy bot cannot win** — 1.8% win rate means the model learns losing play. Need a stronger bot or filtered wins only.

3. **Leduc poker never folds** — teaches the model that folding is never correct, which is exploitable. Need examples of correct folding with J against opponent raises.

4. **Goofspiel strategy is one-dimensional** — "bid == prize" is dominant. Could benefit from examples of intentional over/under-bidding as resource management.

5. **Think diversity is low across all games** — the generation pipeline produces templated reasoning. For training quality, thinks should reference specific game state details (cards in hand, opponent's visible moves, pot odds, etc.).

### Priority Fix Order
1. **Gin rummy thinking pipeline** — highest volume, completely unusable
2. **Leduc poker fold examples** — missing entire action category
3. **Goofspiel think diversity** — functional but improvable
