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

---

## D7: Fixed gin_rummy Re-analysis (397 entries)

**Date**: 2026-03-18
**File analyzed**: `data/game_v3_bot_gin_rummy.jsonl` (397 entries, post-fix)
**Comparison baseline**: 505 canonical gin_rummy entries in `data/canonical/game.jsonl`

### Executive Summary

| Metric | D2 (broken, 440) | D7 (fixed, 397) | Delta |
|--------|-------------------|------------------|-------|
| Unique action sequences | 100% | 99.2% (394/397) | ~same |
| Unique think texts | **1** | **296** | +295x |
| Win rate | 1.8% | 14.4% | +12.6pp |
| Draw rate | 98.2% | 69.8% | -28.4pp |
| Loss rate | 0% | 15.9% | +15.9pp |
| Avg turns | 60.7 | 30.0 | -50.5% |
| Think card-awareness | 0% | 59.8% | fixed |
| Deadwood references | 0% | 54.0% | fixed |
| Recommended keep | **0 (0%)** | **183 (46.1%)** | usable |

**Verdict**: The broken single-template thinking is fully fixed. Think quality is now functional (templated but card/deadwood-aware). Win rate improved 8x from 1.8% to 14.4%. Game length halved. However, 69.8% of games still end in draws, and think reasoning remains shallow (5 template families, not deep strategic reasoning). **183 entries are mergeable (HIGH tier)**, a massive improvement from 0.

---

### 1. Strategy Diversity

- **99.2% unique action sequences** (394/397) — 3 duplicates, down from 100% but negligible.
- **FirstUpcard**: draw=93 (31.0%), pass=207 (69.0%) — reasonable distribution, shows selectivity.
- **Draw decisions**: upcard=1,488 (27.3%), stock=3,953 (72.7%) — stock-heavy but not random (D2 was 49/51 near-random).
- **Discard pattern shows strategic preference for high-value cards**:
  - High-value (T/J/Q/K) discards: 39.4% of all discards
  - Top discarded: Qc(162), Ks(161), Qs(144), Kc(137), Kd(135)
  - This is correct gin rummy strategy: discard high-deadwood cards first
  - D2 had near-uniform discard distribution (no preference) — this is a clear improvement

### 2. Think Tag Quality

**The single broken template is completely gone.** Zero instances of "Organize hand, keep cards that form melds, discard highest deadwood."

- **Total think tags**: 11,905 across 397 entries
- **Unique think texts**: 296 (2.5% of total) — up from 1 in D2
- **Per-entry unique thinks**: min=2, max=41, avg=18.9
  - >=3 unique thinks: 396 entries (99.7%)
  - >=5 unique thinks: 380 entries (95.7%)
  - >=10 unique thinks: 319 entries (80.4%)

**Think quality markers** (% of all 11,905 thinks):
| Marker | Count | % |
|--------|-------|---|
| References specific cards (e.g. Qs, Kh) | 7,122 | 59.8% |
| References melds | 7,236 | 60.8% |
| References deadwood | 6,423 | 54.0% |
| References specific deadwood values | 4,722 | 39.7% |
| References upcard | 5,741 | 48.2% |
| References stock | 3,953 | 33.2% |
| References runs or sets | 0 | 0.0% |

**Think pattern categories** (5 template families):

| Category | Count | % | Example |
|----------|-------|---|---------|
| Discard high deadwood | 4,722 | 39.7% | "Discard Qc (deadwood value 10), not part of any meld." |
| Reject upcard draw | 4,160 | 34.9% | "Upcard doesn't improve hand, draw from stock." |
| Accept upcard draw | 1,488 | 12.5% | "Upcard Ts helps form melds, reducing deadwood." |
| Other (deadwood calcs, sacrifice, etc.) | 992 | 8.3% | "Upcard 6s reduces deadwood from 60 to 48." |
| Forced action | 423 | 3.6% | "Only one legal action available." |
| Knock decision | 120 | 1.0% | "Deadwood is 31, within knock threshold. Knock." |

**Remaining weakness**: Only 0.8% of thinks contain specific deadwood calculations (e.g. "reduces deadwood from 60 to 48"). Zero thinks reference runs or sets by name. The reasoning is card-aware but shallow — it names the card being discarded/drawn but doesn't explain *why* in terms of meld potential, opponent modeling, or hand structure. The dominant template is "Upcard doesn't improve hand, draw from stock" (33.2% of all thinks) — a generic rejection without game-state specificity.

### 3. Game State Complexity

| Metric | D2 (broken) | D7 (fixed) |
|--------|-------------|------------|
| Avg turns | 60.7 | 30.0 |
| Median turns | 64.0 | 26.0 |
| Min turns | 2 | 2 |
| Max turns | 86 | 66 |
| Games 31+ turns | 91.6% | 42.6% |

**Turn distribution**:
| Bucket | Count | % |
|--------|-------|---|
| 1-5 | 17 | 4.3% |
| 6-10 | 41 | 10.3% |
| 11-20 | 97 | 24.4% |
| 21-30 | 73 | 18.4% |
| 31-50 | 101 | 25.4% |
| 51+ | 68 | 17.1% |

- Trivial games (<=5 turns): 17 (4.3%) — should be filtered
- Complex games (>=20 turns): 255 (64.2%)
- Game length is much healthier than D2 — no longer dominated by 60+ turn timeout games

**Deadwood progression** (all 397 entries):
- Start: avg=48.1
- End: avg=31.1
- Min reached: avg=18.8
- Avg reduction: 17.0 points
- Improved: 314 (79.1%), Same: 14 (3.5%), Worsened: 69 (17.4%)

**Knock stats**: 120 entries (30.2%) reach knock phase — compared to D2 where almost none could close. Bot knock deadwood: min=3, max=10, avg=7.4.

### 4. Score Distribution

| Outcome | Count | % |
|---------|-------|---|
| Win (bot knocks) | 57 | 14.4% |
| Loss (opponent knocks) | 63 | 15.9% |
| Draw (timeout/no knock) | 277 | 69.8% |

- **Inferred mean score**: 0.492
- **Score variance**: 0.076
- **D2 comparison**: win rate 1.8% -> 14.4% (8x improvement), but still majority draws
- Bot knock deadwood avg: 7.4 (reasonable — just under knock thresholds of 8-10)
- Opponent knock deadwood avg: 7.2 (opponent is slightly more efficient at closing)

**Concern**: 15.9% loss rate means 63 entries teach the model losing play. These should be filtered or used only as negative examples.

### 5. Complementarity with 505 Canonical Entries

| Metric | Canonical (505) | New (397) | Overlap |
|--------|-----------------|-----------|---------|
| Unique action sequences | 504 | 394 | 2 |
| Unique think texts | 1 | 296 | 0 |
| Avg turns | 31.9 | 30.0 | — |

- **Only 2 overlapping action sequences** — 99.5% of new entries are genuinely new patterns
- **Zero think overlap** — canonical uses the broken single template; new data has 296 unique thinks. This is *completely complementary* on the think dimension.
- Turn distributions are similar (canonical avg 31.9 vs new avg 30.0)
- **The new data is a direct replacement candidate for the canonical gin_rummy thinks**, not just a supplement. The 505 canonical entries have broken thinks that should be replaced.

### 6. Quality Tiering

**Primary tiering** (matching D2 methodology):

| Tier | Count | % | Criteria |
|------|-------|---|----------|
| HIGH | 183 | 46.1% | >=10 turns, >=3 unique thinks, win or deadwood improved |
| MEDIUM | 207 | 52.1% | >=5 turns, >=2 unique thinks |
| LOW | 7 | 1.8% | <5 turns or <2 unique thinks |

HIGH tier breakdown:
- Wins: 54 (bot successfully knocks)
- Draws with deadwood improvement: 129 (bot played well but couldn't close)
- Avg turns: 27.3
- Avg unique thinks per entry: 17.4

**Strict tiering** (HIGH requires win only):

| Tier | Count | % |
|------|-------|---|
| HIGH | 54 | 13.6% |
| MEDIUM | 273 | 68.8% |
| LOW | 70 | 17.6% |

LOW tier breakdown:
- Short games (<5 turns): 17
- Losses (opponent knocks): 63

### Merge Recommendation

**Recommended: merge 183 HIGH-tier entries** into canonical data.

These entries have:
1. Diverse, card-aware thinking (not the broken single template)
2. Sufficient game length (>=10 turns)
3. Positive outcomes (wins or demonstrated deadwood improvement)
4. Unique action patterns not present in canonical

**Additionally consider**: The 505 existing canonical gin_rummy entries have completely broken thinks (single template). The new 183 entries should **replace** the worst canonical entries, not just supplement them. Priority: replace canonical entries that have the broken think template with new HIGH-tier entries.

**Do NOT merge**:
- 7 LOW entries (trivial short games)
- 63 loss entries (teach losing play)
- 144 MEDIUM draw entries without deadwood improvement (stagnant games)

### Remaining Pipeline Issues

1. **Think depth is shallow** — 5 template families, not genuine reasoning. "Upcard doesn't improve hand" (33.2%) tells the model nothing about *why*. Needs: meld-potential reasoning, run/set references, opponent discard tracking.
2. **Zero run/set vocabulary** — thinks never reference "run" or "set" despite these being core gin rummy concepts.
3. **Win rate still low (14.4%)** — majority of games time out. Bot strategy needs improvement to close games.
4. **Knock thinks are mechanistic** — "Deadwood is X, within knock threshold. Knock." doesn't reason about whether knocking is optimal vs continuing.
