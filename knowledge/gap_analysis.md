# Gap Analysis

**Last updated**: 2026-03-22 03:32 UTC

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
| v2.8 | **24.71** | **6.60** | **4.0** | 0.17 | 8192 | 7e-5 | 6691 | **epochs=2 FAILED** — all regressed |
| v2.9 | 26.48 | 8.36 | 6.42 | 0.266 | 8192 | 5e-5 | 5413 | All regressed. Less data = worse everywhere. |
| v2.10 | — | — | — | — | 8192 | 5e-5 | 8017 | **NW V5 + more data, TRAINING** |

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

## Live Leaderboard (Block 7798081) — 7 Environments

| Rank | Miner | GAME | LGC-v2 | LIVEWEB | NAVWORLD | PRINT | SWE-I | SWE-SYNTH |
|------|-------|------|--------|---------|----------|-------|-------|-----------|
| 1 | affshoot | 47.06 | 89.56 | 20.81 | 27.92 | 82.72 | 12.37 | 46.39 |
| 2 | AnastasiaF | 46.51 | 90.00 | 22.71 | 18.68 | 83.60 | 12.00 | 25.00 |
| 3 | wisercat | 46.54 | 89.07 | 18.89 | 27.93 | 82.29 | 8.00 | 29.00 |
| 4 | vera6 | 48.52 | 88.00 | 17.94 | 25.04 | 87.23 | 10.20 | 25.00 |
| 5 | RLStepone | 45.53 | 90.40 | 14.76 | 24.43 | 83.94 | 9.09 | 26.26 |
| 6 | AnastasiaF2 | 37.88 | 80.40 | 19.58 | 24.24 | 83.07 | 8.08 | 31.00 |
| **v2.7** | **ours** | **28.90** | **—** | **13.76** | **12.63** | **—** | **—** | **—** |

**Critical**: We score on 3/7 environments. Competitors score on all 7. With L7 having 64x weight of L1, missing 4 environments is catastrophic for leaderboard rank even with epsilon smoothing.

**Leaderboard shifts since last check**: wisercat dropped from #2 to #3, AnastasiaF rose to #2, vera6 entered at #4. Competition tightening — 6 miners with weight>0.

## Rank-Jump ROI (sorted by impact)

### Tier 0: Environment Coverage (HIGHEST PRIORITY)
We currently cover 3/7 environments. Each missing env contributes ~0 to geometric mean across all subsets containing it. **No amount of improvement in GAME/NAVWORLD/LIVEWEB can compensate for 4 zero envs.**

- **SWE-INFINITE** (0 vs #6=8.08): 39 trajectories canonical. Competitors score 8-12. Need first deployment.
- **SWE-SYNTH**: Being replaced by SWE-INFINITE. Competitors score 25-46. Need coverage.
- **LGC-v2**: User excluded. Competitors score 80-90. Massive gap.
- **PRINT**: User excluded. Competitors score 82-87. Massive gap.

### Tier 1: Existing Environment Improvement
1. **GAME** (28.90 vs #6=37.88, gap=8.98): Only 3/7 games score via SFT. 5 games need GRPO (Phase 3). data-game in Phase 1 bot optimization.
2. **NAVWORLD** (12.63 vs #6=24.24, gap=11.61): V5 format fixes testing in v2.10 (eval running NOW). 1471 V5 entries canonical.
3. **LIVEWEB** (13.76 vs #5=14.76, gap=1.00): Very close to rank 5. 528 entries canonical (+44 since v2.10). Smallest gap — easiest rank jump.

## Critical Data Updates

### NAVWORLD V5 Format Fixes (P0)
data-qqr discovered 3 critical format mismatches in ALL existing NAVWORLD training data:
1. Transport format: training used JSON objects, eval uses Chinese text strings
2. Prompts: training used English, eval uses Chinese
3. Tool schema: training missing parameters vs eval

**V5 CANONICAL**: **1420 entries** (incremental merges continuing), 99.8% quality, all eval-aligned, HF synced. **v2.10 APPROVED and launching.**

### GAME v10 Final (SFT)
2260 entries: gin_rummy 1484, goofspiel 480, leduc 296. Zero-score games removed. GRPO needed for 5 remaining games.

### SWE-INFINITE
**38 real trajectories** canonical (up from 15), validation batch running. Need 100+ for meaningful eval scores. data-swe reports 6% fix rate bottleneck, ~90-140 expected from current batch.

## v2.8 COMPLETED — epochs=2 TOTAL FAILURE

| Env | v2.8 (ep=2, lr=7e-5) | v2.7 (ep=1, lr=5e-5) | Delta |
|-----|----------------------|----------------------|-------|
| GAME | **24.71** | 28.90 | **-14%** |
| NAVWORLD | **6.60** | 12.63 | **-48%** |
| LIVEWEB | **4.0** | 13.76 | **-71%** |

- Loss 0.17 (low) but ALL envs regressed catastrophically
- **Root cause**: epochs=2 causes overfitting across the board, not just LIVEWEB
- Also changed lr (7e-5 vs 5e-5) — two variables, but regression magnitude points to epochs
- **Verdict**: epochs=2 is permanently killed. NEVER use >1 epoch with this data volume.
- **M2 now FREE** — v2.10 should launch immediately

## v2.9 EVAL (M1) — LOSING to v2.7 (partial results)

| Env | v2.9 (3-game, 5413) | v2.7 (all-game, 6204) | Delta |
|-----|---------------------|----------------------|-------|
| GAME | **26.48** | 28.90 | **-8%** |
| NAVWORLD | **8.36** | 12.63 | **-34%** |
| LIVEWEB | **6.42** | 13.76 | **-53%** |

- **All envs regressed**. Early partial (54/100) showed GAME 28.72, but final 100-sample result is 26.48.
- **LIVEWEB finding**: Reduced total data (5413 vs 6204) crushed LIVEWEB (-53%). Small datasets most sensitive to volume.
- **Conclusion**: Data volume protects all environments. Keep all GAME data including zero-score games.
- **Lesson**: Removing data always hurts. The generic training signal from zero-score games benefits generalization across all envs.
- **NOTE**: Canonical not yet updated to v10 by data-game. Used 3101 (filtered from old 5888) not 2260.

## v2.10 EVAL IN PROGRESS (M2) — NW V5 + more data

### Partial Results (LIVEWEB final, GAME/NW in progress)

| Env | v2.10 | v2.7 | Delta | Samples | Notes |
|-----|-------|------|-------|---------|-------|
| GAME | ~14.4 | 28.90 | **-50%** | 28/100 | ALARMING if holds. High variance, need full 100. |
| NAVWORLD | ~13.1 | 12.63 | **+4%** | 42/100 | Modest V5 improvement. Not the 18-22 jump expected. |
| LIVEWEB | **7.92** | 13.76 | **-42%** | 100/100 | **34 cache errors** — Stooq API limit, page fetch failures. Result INVALIDATED by infra issues. Real model performance ~12.0 on valid tasks. |

### Analysis (updated 03:32 UTC — more samples confirm regression)
- **ALL THREE envs regressing vs v2.7**. v2.10 is a total failure.
- **NAVWORLD V5**: Initially looked +4% at 42 samples, dropped to -16% at 63 samples. Format fixes did NOT help.
- **GAME**: Persistent -47% regression. More data did NOT help despite v2.9 finding.
- **LIVEWEB**: -42% but 34% cache errors inflate the loss. Real model perf ~12 on valid tasks.
- **Primary suspect: SWE-I 215 entries** — only new data type, low quality (5% fix rate), radically different format. v2.7 had zero SWE-I.
- **v2.11 redesigned**: Remove SWE-I only (single variable). If GAME/LW recover → SWE-I confirmed toxic.

### Config
- lr=5e-5, seq=8192, epochs=1 (same as v2.7)
- Data: GAME 5888 + NW V5 1430 + LW 484 + SWE-I 215 = **8017** total
- Training: COMPLETE. Eval started 02:42 UTC 2026-03-22 on M2.

## Action Items
- [x] v2.6 + v2.7 lr A/B → lr=5e-5 wins
- [x] v2.8 eval → epochs=2 FAILED, all regressed
- [x] v2.9 eval → less data hurts, all regressed vs v2.7
- [x] NAVWORLD V5 complete (1471 canonical)
- [x] v2.10 designed + approved + training complete
- [ ] **v2.10 eval running on M2** (GAME 1/100, started 02:32 UTC 2026-03-22)
- [ ] v2.11 data prep on M1 (directive sent to Trainer)
- [ ] GAME GRPO framework (Phase 3 — data-game in Phase 1 bot optimization)
- [ ] SWE-INFINITE scale-up (39→100+ trajectories)
- [ ] **FLAG TO USER**: LGC-v2 + PRINT exclusion is strategically costly with 7-env leaderboard
