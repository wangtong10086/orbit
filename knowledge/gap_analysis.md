# Gap Analysis

**Last updated**: 2026-03-19 (Strategist loop 45)
**Status**: v2 training ETA passed (2026-03-18 ~19:15 UTC), **machine unreachable** — cannot verify completion

## Live Leaderboard (Block 7776423)

| Rank | Miner | GAME | NAVWORLD | SWE-SYNTH | LIVEWEB | LGC-v2 | PRINT | Weight |
|------|-------|------|----------|-----------|---------|--------|-------|--------|
| 1 | wisercat | 47.14 | 24.11 | 42.00 | 19.47 | 87.90 | 80.90 | 0.508 |
| 2 | affshoot | 49.44 | 16.28 | 43.00 | 19.17 | 89.11 | 79.80 | 0.254 |
| 3 | vera6 | 50.56 | 22.52 | 30.00 | 19.44 | 90.40 | 82.81 | 0.127 |
| 4 | RLStepone | 48.73 | 20.34 | 38.00 | 15.98 | 87.60 | 80.61 | 0.063 |
| 5 | AnastasiaFantasy | 40.92 | 22.16 | 36.36 | 17.05 | 83.20 | 81.05 | 0.032 |
| 6 | EdmondMillion | 45.55 | 20.69 | 38.00 | 14.55 | 86.80 | 81.73 | 0.016 |

**Changes from Block 7772891**: wisercat ↑#1 (was #3), affshoot ↓#2 (was #1), EdmondMillion NEW at #6.

**Notable**: EdmondMillion UID 68 has near-identical scores to wisercat (GAME 47.05, NAVWORLD 24.27, SWE-SYNTH 42.00) but weight=0 — Pareto-filtered (registered later).

## 6-env GM Analysis (ALL envs matter for scoring)

**Competitor GMs (approximate)**:
- wisercat #1: (47.14 × 24.11 × 42.00 × 19.47 × 87.90 × 80.90)^(1/6) ≈ 43.3
- affshoot #2: (49.44 × 16.28 × 43.00 × 19.17 × 89.11 × 79.80)^(1/6) ≈ 40.9
- vera6 #3: (50.56 × 22.52 × 30.00 × 19.44 × 90.40 × 82.81)^(1/6) ≈ 41.7

**Why wisercat leads**: Most balanced — no env below 19.47. affshoot has NAVWORLD=16.28 (weakest link drags L6 GM down).

## Gap Table (vs #1 wisercat)

| Env | #1 Score | Field Range | Our v2 Data | Expected Score | Gap to #1 | Priority |
|-----|----------|-------------|-------------|----------------|-----------|----------|
| GAME | 47.14 | 40.9-50.6 | 2641 entries | 25-35 | -12 to -22 | P1 |
| NAVWORLD | 24.11 | 16.3-24.3 | 2248 entries | 5-8 | -16 to -19 | **P0** |
| SWE-SYNTH | 42.00 | 30.0-43.0 | 983 entries | 10-25 | -17 to -32 | P1 |
| LIVEWEB | 19.47 | 14.6-19.5 | 18 entries | 15-20 | -5 to +1 | Maintain |
| LGC-v2 | 87.90 | 83.2-90.4 | **0 in v2** ⚠️ | 0 (not trained) | **-87.9** | 🔴 CRITICAL |
| PRINT | 80.90 | 74.1-82.8 | **0 in v2** ⚠️ | 0 (not trained) | **-80.9** | 🔴 CRITICAL |

## 🔴 STRATEGIC ERROR: LGC-v2/PRINT Exclusion

**Problem**: v2 excluded LGC-v2 and PRINT. All 6 top miners score 83-90 on LGC-v2 and 74-83 on PRINT. These are "table stakes" — easy to score well with basic data. Deploying with 0 on these envs means:
- L6 subset (weight 192, 32x L1) would be devastated
- All L2+ subsets containing LGC-v2 or PRINT get near-zero contribution
- We'd be Pareto-dominated by everyone

**Fix**: Data already exists (LGC-v2 1500, PRINT 1500 — prepared for v1). Re-include in v3 training. Zero additional effort.

**User instruction**: "Don't spend effort on LGC-v2 and PRINT, only maintain coverage." Including existing subsampled data IS maintaining coverage.

## v3 Data Plan (6-env, corrected)

| Env | Count | Source |
|-----|-------|--------|
| GAME | 2641 + 183 (D7 HIGH gin_rummy) | canonical + v3 staging |
| NAVWORLD | 2248 + 400 (D6 Phase 1) | canonical + new diverse data |
| SWE-SYNTH | 983 | canonical |
| LIVEWEB | 18 | canonical |
| LGC-v2 | 1500 | canonical (already prepared) |
| PRINT | 1500 | canonical (already prepared) |
| **Total** | **~8490** | |

## ROI Analysis (updated for Block 7776423)

| Action | Impact | Effort | ROI |
|--------|--------|--------|-----|
| Re-include LGC-v2+PRINT (1500 each) | **Prevents total L6 collapse** | Zero (data exists) | **∞** |
| NAVWORLD D6 Phase 1 diversity (+400) | Break 5-template ceiling | Medium | **Highest** |
| GAME D7 gin_rummy merge (+183 HIGH) | Better gin_rummy learning | Low | High |
| Resolve machine access | Unblock all work | User action needed | **BLOCKER** |

## Action Items

- [x] D1-D7 complete
- [ ] 🔴 **Machine unreachable** — user must check/restart GPU rental
- [ ] 🔴 **v3 design**: re-include LGC-v2/PRINT (1500 each, data ready)
- [ ] **D6 Phase 1**: execute NAVWORLD diversity expansion (400 new entries)
- [ ] **D7 merge**: 183 HIGH gin_rummy entries → canonical
- [ ] v2 eval results → diagnose per-env performance
- [ ] v3 experiment YAML design (pending v2 results)
