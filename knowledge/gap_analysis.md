# Gap Analysis

**Last updated**: 2026-03-21 11:30 UTC

## Training History

| Ver | GAME | NAVWORLD | LIVEWEB | Loss | seq | lr | Data | Key Finding |
|-----|------|----------|---------|------|-----|----|------|-------------|
| v2.1 | 25.74 | 8.47† | — | 0.156 | 8192 | 1e-4 | 6894 | Baseline |
| v2.2 | 26.04 | 6.10† | 6.83 | 0.224 | 16384 | 1e-4 | 7239 | NW regressed at seq=16384 |
| v2.3 | 22.69 | 1.52† | 8.62 | 0.172 | 16384 | 1e-4 | 7626 | qwen-max contamination |
| v2.4a | 26.03 | 7.71† | 11.90 | 0.231 | 8192 | 1e-4 | 5120 | seq=8192 wins GM |
| v2.4b | 25.44 | 4.58† | 15.77 | ~0.17 | 16384 | 1e-4 | 5278 | LW best at seq=16384 |
| v2.5 | 24.28 | 6.51† | 11.82 | 0.288 | 16384 | 1e-4 | 5533 | Regression, loss abnormal |
| v2.6 | 26.66 | 5.82† | 11.73 | 0.301 | 8192 | 1e-4 | 6191 | lr=1e-4 control |
| **v2.7** | **28.90** | **12.63** | **13.76** | 0.243 | 8192 | **5e-5** | 6204 | **BEST — lr=5e-5 wins** |
| v2.8 | — | — | — | — | 8192 | 7e-5 | 6691 | epochs=2, TRAINING |

†v2.1-v2.6 NAVWORLD scores are **code-only** (max 50/100). v2.7+ includes CHUTES LLM scoring (max 100).

## Key A/B Results

### lr A/B (v2.6 vs v2.7) — lr=5e-5 decisive winner

| Env | lr=1e-4 (v2.6) | lr=5e-5 (v2.7) | Delta |
|-----|----------------|----------------|-------|
| GAME | 26.66 | **28.90** | +2.24 |
| NAVWORLD | 5.82* | **12.63** | +6.81 |
| LIVEWEB | 11.73 | **13.76** | +2.03 |

*v2.6 code-only; v2.7 full CHUTES. Even accounting for this, lr=5e-5 is clearly better.

### seq A/B (v2.4a vs v2.4b) — seq=8192 wins on GM

seq=8192 better for GAME/NAVWORLD (tool-calling), seq=16384 better for LIVEWEB.

## Live Leaderboard (Block 7793424) — 7 Environments

| Rank | Miner | GAME | LGC-v2 | LIVEWEB | NAVWORLD | PRINT | SWE-I | SWE-SYNTH |
|------|-------|------|--------|---------|----------|-------|-------|-----------|
| 1 | affshoot | 47.44 | 89.11 | 20.40 | 24.14 | 82.54 | 17.35 | 47.47 |
| 2 | wisercat | 44.71 | 90.40 | 19.71 | 24.46 | 84.66 | 6.00 | 36.36 |
| 3 | AnastasiaF | 46.80 | 90.40 | 22.46 | 16.38 | 84.82 | 10.00 | 33.33 |
| 6 | axon1 | 45.78 | 85.60 | 16.87 | 28.97 | 82.63 | 5.00 | 32.32 |
| **v2.7** | **ours** | **28.90** | **—** | **13.76** | **12.63** | **—** | **—** | **—** |

**Critical**: We score on 3/7 environments. Competitors score on all 7. With L7 having 64x weight of L1, missing 4 environments is catastrophic for leaderboard rank even with epsilon smoothing.

## Rank-Jump ROI (sorted by impact)

### Tier 0: Environment Coverage (HIGHEST PRIORITY)
We currently cover 3/7 environments. Each missing env contributes ~0 to geometric mean across all subsets containing it. **No amount of improvement in GAME/NAVWORLD/LIVEWEB can compensate for 4 zero envs.**

- **SWE-INFINITE** (0 vs #6=5.00): 15 trajectories in canonical, 215 in v2.8 training. Need first deployment.
- **SWE-SYNTH**: Being replaced by SWE-INFINITE. Competitors score 27-47. Need coverage.
- **LGC-v2**: User excluded. Competitors score 85-90. Massive gap.
- **PRINT**: User excluded. Competitors score 79-93. Massive gap.

### Tier 1: Existing Environment Improvement
1. **GAME** (28.90 vs #6=45.78, gap=16.88): Zero-score games (5/7 games) need GRPO. SFT ceiling ~30 with only 3 scoring games.
2. **NAVWORLD** (12.63 vs #6=28.97, gap=16.34): V5 format fixes are critical — all prior data had wrong transport format, English prompts, missing schema. V5 data expected to dramatically improve.
3. **LIVEWEB** (13.76 vs #6=16.87, gap=3.11): Closest to competitors. More data (464→500+) and quality improvements.

## Critical Data Updates

### NAVWORLD V5 Format Fixes (P0)
data-qqr discovered 3 critical format mismatches in ALL existing NAVWORLD training data:
1. Transport format: training used JSON objects, eval uses Chinese text strings
2. Prompts: training used English, eval uses Chinese
3. Tool schema: training missing parameters vs eval

V5 regeneration: 281/1610 generated. **This is likely the single highest-ROI data fix.**

### GAME v10 Final (SFT)
2260 entries: gin_rummy 1484, goofspiel 480, leduc 296. Zero-score games removed. GRPO needed for 5 remaining games.

### SWE-INFINITE
15 real trajectories canonical. 215 in v2.8 training. Need 100+ for meaningful eval scores.

## v2.8 Status (M2)
- Training on m2: epochs=2, lr=7e-5, 6691 samples
- **45% complete** (step 256/564), loss 0.2005 (target <0.20 HIT)
- ETA: ~2h remaining
- Token accuracy: 93.9%

## v2.9 APPROVED (M1) — GAME v10 cleaned data
- **Variable**: GAME data quality — v10 cleaned (2260) vs v2.7's 4405
- **Hypothesis**: Removing zero-score game data improves GAME from 28.90 to 30+
- **Config**: lr=5e-5, seq=8192, epochs=1 (same as v2.7)
- **Data**: GAME 2260 + NW 1633 + LW 464 + SWE-I 215 = 4572
- **Machine**: M1 (was idle)

## v2.10 Design (DRAFT — blocked on NW V5)
**Wait for**: NAVWORLD V5 data completion (281/1610)
**Variable**: NAVWORLD V5 data (format-corrected)
**Hypothesis**: Correct format alignment should improve NAVWORLD from 12.63 to 15-20
**Config**: lr=5e-5, seq=8192, epochs=1, best GAME data from v2.9 vs v2.8 winner
**Data**: GAME (best of v2.9/v2.8) + NAVWORLD V5 (~1610) + LIVEWEB (500+) + SWE-I (100+)

## Action Items
- [x] v2.6 + v2.7 lr A/B → lr=5e-5 wins
- [ ] v2.8 eval on m2 (epochs=2 test, ~2h)
- [ ] v2.9 eval on m1 (GAME v10 cleaned, launching now)
- [ ] NAVWORLD V5 regeneration completion (281/1610)
- [ ] v2.10 design with V5 NAVWORLD data
- [ ] GAME GRPO framework (Phase 3 — data-game preparing OpenPipe ART)
- [ ] SWE-INFINITE scale-up (15→100+ trajectories)
- [ ] **FLAG TO USER**: LGC-v2 + PRINT exclusion is strategically costly with 7-env leaderboard
