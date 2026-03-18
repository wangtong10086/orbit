# Gap Analysis

**Last updated**: 2026-03-18 (loop 4)
**Status**: PRE-DEPLOYMENT — competitor data from LIVE leaderboard (Block 7771839)

## Current Position

Not on leaderboard. No model deployed. Live competitor data from Trainer's leaderboard pull.

## Live Leaderboard (Block 7771839)

| Rank | Miner | GAME | NAVWORLD | SWE-SYNTH | LIVEWEB | LGC-v2 | PRINT |
|------|-------|------|----------|-----------|---------|--------|-------|
| 1 | affshoot | 50.75 | 16.75 | 56.84 | 19.36 | 89.88 | 77.49 |
| 2 | AnastasiaFantasy | 41.63 | 24.56 | 39.00 | 16.08 | 81.53 | 80.42 |
| 3 | vera6 | 50.48 | 24.05 | 25.00 | 18.95 | 90.69 | 81.38 |
| 4 | RLStepone | 49.66 | 21.76 | 34.00 | 15.80 | 88.26 | 79.29 |

**Notable**: deepresearch001 has SWE-SYNTH ~60.61 (highest single-env SWE-SYNTH score).

## Gap Table (vs #1 per env)

| Env | Best Score | Best Miner | Our v11 | Gap to Best | SFT Ceiling | Priority |
|-----|-----------|------------|---------|-------------|-------------|----------|
| SWE-SYNTH | 56.84 | affshoot | ~31 | -25.8 | ~35-40 | P1 |
| GAME | 50.75 | affshoot | 22.6 | -28.2 | ~40-50 | P1 |
| NAVWORLD | 24.56 | AnastasiaFantasy | 5.7 | -18.9 | ~15-20 | **P0** |
| LIVEWEB | 19.36 | affshoot | ~24 | +4.6 | ~24 | P3 (maintain) |
| LGC-v2 | 90.69 | vera6 | ~95 | +4.3 | 95 | Maintain |
| PRINT | 81.38 | vera6 | ~80 | -1.4 | ~82 | Maintain |

## Geometric Mean Analysis

**#1 (affshoot) GM**: (50.75 × 16.75 × 56.84 × 19.36 × 89.88 × 77.49)^(1/6) ≈ 42.5

**Our v11-equivalent GM**: (22.6 × 5.7 × 31 × 24 × 95 × 80)^(1/6) ≈ 31.5

**Gap to #1**: ~11 GM points. Smaller than previously estimated (was ~21).

**Key insight**: affshoot is #1 despite weak NAVWORLD (16.75) and average LGC-v2 (89.88). They win through strong SWE-SYNTH (56.84) + GAME (50.75). This validates "balanced > dominant" but also shows SWE-SYNTH is more important than we thought.

## Revised Rank-Jump ROI Analysis

| Env | Our v11 → Realistic Target | GM Impact | Effort | ROI |
|-----|---------------------------|-----------|--------|-----|
| NAVWORLD | 5.7 → 18 | **+6.4 GM** | Medium (quality filter + DPO) | **Highest** |
| GAME | 22.6 → 40 | +4.5 GM | Medium (new bots + more data) | High |
| SWE-SYNTH | 31 → 40 | +1.6 GM | Low (seq=8192 unlocks 49% data) | High (cheap) |
| PRINT | 80 → 82 | +0.2 GM | Low | Low |
| LIVEWEB | 24 → 24 | 0 | None (already competitive) | N/A |
| LGC-v2 | 95 → 95 | 0 | None (already competitive) | N/A |

## Strategic Conclusions (revised with live data)

1. **NAVWORLD is still #1 lever** — 5.7→18 contributes +6.4 GM. Also: best NAVWORLD is only 24.56, so catching up is feasible.
2. **SWE-SYNTH gap is larger than expected** — affshoot at 56.84, we're at ~31. seq=8192 is critical for v2.
3. **GAME competition is tighter** — top 3 all cluster 49-51, not 63 as old data said. SFT ceiling of 40-50 puts us in contention.
4. **LIVEWEB and LGC-v2 are strengths** — our v11 scores are competitive or better than current #1. Maintain, don't optimize.
5. **PRINT is nearly there** — 80 vs 81 gap is trivial.
6. **affshoot's weakness is NAVWORLD** (16.75) — if we excel at NAVWORLD we gain massive rank advantage in subsets containing it.

## Action Items

- [x] Revised v1 to include all 6 envs (rev2/rev3)
- [x] Trainer: fixed Forge CLI, reported live leaderboard
- [x] Data: all canonical files cleaned and in place (7664 verified)
- [x] File permissions: resolved via directory-level workaround
- [x] Strategist: v1 APPROVED (loop 3)
- [ ] **Trainer: launch v1 training** (approved, awaiting execution)
- [ ] Trainer: run eval (GAME + NAVWORLD, 100+ samples each)
- [ ] Strategist: analyze v1 results → design v2
- [ ] v2 prep: NAVWORLD quality filter, SWE-SYNTH seq=8192, GAME bot expansion
