# Gap Analysis

**Last updated**: 2026-03-18 14:16 UTC
**Status**: PRE-DEPLOYMENT — v2 training in progress, ETA ~19:15 UTC

## ⚠️ CRITICAL: Scoring Uses ALL 6 Environments

Previous analysis assumed 4-env scoring. **Live leaderboard confirms 6-env scoring** (GAME, LGC-v2, LIVEWEB, NAVWORLD, PRINT, SWE-SYNTH). All competitors have high LGC-v2 (70-90) and PRINT (62-83) scores.

v2 trains on only 4 envs. LGC-v2/PRINT coverage depends on base model retention after fine-tuning.

## Live Leaderboard (Block 7772891, 6-env)

| Rank | Miner | GAME | LGC-v2 | LIVEWEB | NAVWORLD | PRINT | SWE-SYNTH | Weight |
|------|-------|------|--------|---------|----------|-------|-----------|--------|
| 1 | affshoot | 50.03 | 90.20 | 19.08 | 15.72 | 79.27 | 53.19 | 0.508 |
| 2 | vera6 | 50.59 | 90.40 | 19.11 | 25.12 | 82.90 | 27.00 | 0.254 |
| 3 | wisercat | 47.06 | 86.80 | 18.07 | 23.88 | 80.30 | 39.39 | 0.127 |
| 4 | AnastasiaFantasy | 40.84 | 81.60 | 16.53 | 24.84 | 81.25 | 40.00 | 0.063 |
| 5 | RLStepone | 49.37 | 87.55 | 16.31 | 21.88 | 80.90 | 39.00 | 0.032 |
| 6 | coffie3 | 41.56 | 82.43 | 16.38 | 21.69 | 74.07 | 46.00 | 0.016 |

**Changes from Block 7771839**: wisercat NEW at #3, vera6 ↑#2, AnastasiaFantasy ↓#4, coffie3 NEW at #6.

## Gap Table (vs #1 affshoot)

| Env | #1 Score | Competitor Range | Our v11 | Gap to #1 | Priority |
|-----|----------|-----------------|---------|-----------|----------|
| GAME | 50.03 | 40.8-50.6 | 22.6 | -27.4 | P1 |
| LGC-v2 | 90.20 | 73.9-90.4 | ~85* | -5.2 | Maintain |
| LIVEWEB | 19.08 | 14.5-19.1 | ~24 | +4.9 | Maintain |
| NAVWORLD | 15.72 | 15.7-25.1 | 5.7 | -10.0 | **P0** |
| PRINT | 79.27 | 62.5-82.9 | ~75* | -4.3 | Maintain |
| SWE-SYNTH | 53.19 | 21.0-56.6 | ~31 | -22.2 | P1 |

*LGC-v2/PRINT estimates based on Qwen3-32B base model capability (not eval'd)

## 6-env GM Analysis

**Competitor GMs** (approximate):
- affshoot: (50.0 × 90.2 × 19.1 × 15.7 × 79.3 × 53.2)^(1/6) ≈ 42.4
- vera6: (50.6 × 90.4 × 19.1 × 25.1 × 82.9 × 27.0)^(1/6) ≈ 42.0
- wisercat: (47.1 × 86.8 × 18.1 × 23.9 × 80.3 × 39.4)^(1/6) ≈ 41.5

**Our v2 scenarios (6-env)**:

| Scenario | GAME | LGC-v2 | LIVEWEB | NAV | PRINT | SWE | 6-env GM |
|----------|------|--------|---------|-----|-------|-----|----------|
| Optimistic (LGC/PRINT retain) | 35 | 80 | 22 | 10 | 70 | 25 | ~32.5 |
| Conservative (LGC/PRINT retain) | 25 | 70 | 18 | 6 | 60 | 15 | ~24.2 |
| Worst (LGC/PRINT degrade) | 25 | 30 | 18 | 6 | 30 | 15 | ~17.5 |

**NAVWORLD remains the GM killer** — at 5.7, it drags everything down. But LGC-v2/PRINT coverage is now the #2 risk.

## ROI Analysis (6-env scoring)

| Env | Current → Target | 6-env GM Impact | Effort | ROI |
|-----|-----------------|-----------------|--------|-----|
| NAVWORLD | 5.7 → 18 | **+6.5 GM** | Medium (DPO) | **Highest** |
| GAME | 22.6 → 40 | +3.2 GM | Low (data done) | High |
| SWE-SYNTH | 31 → 40 | +1.2 GM | Low (seq=8192) | High |
| LGC-v2/PRINT | maintain 70+/60+ | avoid -7 GM penalty | Low (include data) | **Critical if degraded** |
| LIVEWEB | 24 → 24 | 0 | None | N/A |

## Rank-Jump Opportunities (per subset)

Key insight: NAVWORLD is where we can jump the most ranks. Top NAVWORLD is vera6 at 25.12 — the field is compressed (15.7-25.1). Even 15+ would be competitive in many subsets.

GAME is also compressed (40.8-50.6) — hard to rank-jump without significant improvement.

SWE-SYNTH has the widest spread (21.0-56.6) — room to differentiate.

## Action Items

- [x] GAME data recovered + bot data generated (2641 entries)
- [x] v2 experiment approved and RUNNING (ETA ~19:15 UTC)
- [ ] **v2 eval MUST include LGC-v2 + PRINT** — assess coverage degradation
- [ ] v2 eval → diagnose per-env performance (all 6 envs)
- [ ] If LGC-v2/PRINT degraded → v2a adds back 1500+1500 maintenance data
- [ ] If GM<20 → v2a iteration (fix weakest env)
- [ ] Phase 3: NAVWORLD DPO (highest ROI)
