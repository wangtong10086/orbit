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

**V5 CANONICAL MERGED**: 1348 entries, 99.8% quality, all eval-aligned, HF synced. Old 951 buggy entries fully replaced. **v2.10 APPROVED to use this data.**

### GAME v10 Final (SFT)
2260 entries: gin_rummy 1484, goofspiel 480, leduc 296. Zero-score games removed. GRPO needed for 5 remaining games.

### SWE-INFINITE
15 real trajectories canonical. 215 in v2.8 training. Need 100+ for meaningful eval scores.

## v2.8 Results (M2) — epochs=2 OVERFITS
- Training: 564 steps, final loss ~0.17
- **LIVEWEB = 4.0** — catastrophic regression from v2.7's 13.76
- GAME and NAVWORLD: eval still completing
- **Root cause**: epochs=2 overfits small datasets (LIVEWEB only 438 samples, seen twice)
- **Conclusion**: epochs=2 is NOT viable. epochs=1 + lr=5e-5 (v2.7) remains best config.
- Low loss ≠ good eval: 0.17 loss but LIVEWEB collapsed. Overfitting confirmed.

## v2.9 COMPLETE (M1) — eval deploying
- **Variable**: GAME data quality — 3-game filter (3101) vs v2.7's all-game (4405)
- Training COMPLETE: loss 0.266, LoRA merged, sglang deploying for eval
- **Data**: GAME 3101 + NW 1633 + LW 464 + SWE-I 215 = 5413
- Eval results expected next loop
- **NOTE**: Canonical not yet updated to v10 by data-game. Used 3101 (filtered from old 5888) not 2260.

## v2.10 APPROVED — NAVWORLD V5 format-corrected
- **Variable**: NW V5 data (1348 entries, format-corrected) vs v2.7's buggy NW data
- **Hypothesis**: NAVWORLD 12.63 → 18-22 with correct format alignment
- **Config**: lr=5e-5, seq=8192, epochs=1 (same as v2.7)
- **Data**: canonical GAME + NW V5 1348 + LW 464 + SWE-I 215
- **Machine**: first available after v2.8/v2.9 evals complete
- **Blocker cleared**: NW V5 merged to canonical + HF

## Action Items
- [x] v2.6 + v2.7 lr A/B → lr=5e-5 wins
- [ ] v2.8 eval on m2 (epochs=2 test, ~2h)
- [ ] v2.9 eval on m1 (GAME v10 cleaned, launching now)
- [ ] NAVWORLD V5 regeneration completion (281/1610)
- [ ] v2.10 design with V5 NAVWORLD data
- [ ] GAME GRPO framework (Phase 3 — data-game preparing OpenPipe ART)
- [ ] SWE-INFINITE scale-up (15→100+ trajectories)
- [ ] **FLAG TO USER**: LGC-v2 + PRINT exclusion is strategically costly with 7-env leaderboard
