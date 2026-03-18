# Gap Analysis

**Last updated**: 2026-03-18
**Status**: PRE-DEPLOYMENT — 4-env scoring (GAME, NAVWORLD, SWE-SYNTH, LIVEWEB)

## Active Environments (4个, LGC-v2和PRINT不参与)

## Live Leaderboard (Block 7771839, 4-env)

| Rank | Miner | GAME | NAVWORLD | SWE-SYNTH | LIVEWEB | 4-env GM |
|------|-------|------|----------|-----------|---------|----------|
| 1 | affshoot | 50.75 | 16.75 | 56.84 | 19.36 | ~31.4 |
| 2 | AnastasiaFantasy | 41.63 | 24.56 | 39.00 | 16.08 | ~28.5 |
| 3 | RLStepone | 49.66 | 21.76 | 34.00 | 15.80 | ~28.0 |
| 4 | vera6 | 50.48 | 24.05 | 25.00 | 18.95 | ~27.8 |

## Gap Table

| Env | Best Score | Our v11 | Gap | SFT Ceiling | Priority |
|-----|-----------|---------|-----|-------------|----------|
| GAME | 50.75 | 22.6 | -28 | ~40-50 | P1 |
| NAVWORLD | 24.56 | 5.7 | -19 | ~15-20 | **P0** |
| SWE-SYNTH | 56.84 | ~31 | -26 | ~35-40 | P1 |
| LIVEWEB | 19.36 | ~24 | **+5** | ~24 | Maintain |

## 4-env GM Analysis

**#1 (affshoot)**: (50.75 × 16.75 × 56.84 × 19.36)^(1/4) ≈ 31.4

**Our v2 estimates** (4-env):
- Conservative: (25 × 6 × 15 × 20)^(1/4) ≈ 14.5
- Target: (30 × 8 × 20 × 22)^(1/4) ≈ 18.1
- Optimistic: (35 × 10 × 25 × 24)^(1/4) ≈ 21.7

**NAVWORLD is the GM killer** — at 5.7, it drags everything down. Must break SFT plateau (Phase 3 DPO).

## ROI Analysis (4-env GM impact)

| Env | Current → Target | 4-env GM Impact | Effort | ROI |
|-----|-----------------|-----------------|--------|-----|
| NAVWORLD | 5.7 → 18 | **+8.2 GM** | Medium (DPO) | **Highest** |
| GAME | 22.6 → 40 | +3.8 GM | Low (data done) | High |
| SWE-SYNTH | 31 → 40 | +1.4 GM | Low (seq=8192) | High |
| LIVEWEB | 24 → 24 | 0 | None | N/A |

## Action Items

- [x] GAME data recovered + bot data generated (2416 entries)
- [x] Non-eval games removed (blackjack/euchre/etc)
- [x] LGC-v2/PRINT excluded from training
- [x] v2 experiment approved (4-env, seq=8192)
- [ ] Trainer: launch v2
- [ ] v2 eval → diagnose per-env performance
- [ ] If GM<20 → v2a iteration
- [ ] Phase 3: NAVWORLD DPO (highest ROI)
