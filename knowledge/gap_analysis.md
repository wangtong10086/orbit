# Gap Analysis

**Last updated**: 2026-03-19 (Strategist loop 46)
**Status**: Machine ONLINE. v2 training likely complete (GPUs at 0%). Trainer directed to check + eval.

## Live Leaderboard (Block 7776573)

| Rank | Miner | GAME | NAVWORLD | SWE-SYNTH | LIVEWEB | LGC-v2 | PRINT | Weight |
|------|-------|------|----------|-----------|---------|--------|-------|--------|
| 1 | affshoot | 49.44 | 16.28 | 43.00 | 19.16 | 89.11 | 79.80 | 0.508 |
| 2 | vera6 | 50.56 | 22.52 | 30.00 | 19.44 | 90.40 | 82.56 | 0.254 |
| 3 | RLStepone | 48.73 | 20.34 | 38.00 | 15.93 | 87.60 | 80.81 | 0.127 |
| 4 | AnastasiaFantasy | 40.78 | 22.16 | 37.00 | 17.16 | 83.20 | 80.83 | 0.063 |
| 5 | EdmondMillion-19 | 45.55 | 20.69 | 38.00 | 14.57 | 86.80 | 81.73 | 0.032 |
| 6 | coffie3 | 40.26 | 20.72 | 42.00 | 16.86 | 83.61 | 74.19 | 0.016 |

**Changes from Block 7776423**: wisercat DROPPED OFF (was #1!). affshoot back to #1. coffie3 new at #6.
**Leaderboard is volatile** — rankings shift significantly between blocks. Balance is key.

**Notable**: EdmondMillion UID 68 (weight=0) has: GAME 47.05, NAVWORLD 24.27, SWE-SYNTH 42.00 — would be #1 if not Pareto-filtered.

## 6-env GM Analysis (ALL envs matter for scoring)

**Competitor GMs (approximate, 6-env)**:
- affshoot #1: (49.44 × 16.28 × 43.00 × 19.16 × 89.11 × 79.80)^(1/6) ≈ 40.8
- vera6 #2: (50.56 × 22.52 × 30.00 × 19.44 × 90.40 × 82.56)^(1/6) ≈ 41.6
- RLStepone #3: (48.73 × 20.34 × 38.00 × 15.93 × 87.60 × 80.81)^(1/6) ≈ 40.4

**affshoot leads by weight but vera6 has higher GM** — affshoot's NAVWORLD=16.28 is the weakest link among top 3. Pareto filter + registration timing matter.

## Gap Table (vs #1 affshoot)

| Env | #1 Score | Field Range | Our v2 Data | Expected Score | Gap to #1 | Priority |
|-----|----------|-------------|-------------|----------------|-----------|----------|
| GAME | 49.44 | 40.3-50.6 | 2641 entries | 25-35 | -14 to -24 | P1 |
| NAVWORLD | 16.28 | 16.3-24.3 | 2248 entries | 5-8 | -8 to -11 | **P0** |
| SWE-SYNTH | 43.00 | 30.0-43.0 | 983 entries | 10-25 | -18 to -33 | P1 |
| LIVEWEB | 19.16 | 14.6-19.4 | 18 entries | 15-20 | -4 to +1 | Maintain |
| LGC-v2 | 89.11 | 83.2-90.4 | 1500 in canonical | 70-85 | -4 to -19 | Coverage |
| PRINT | 79.80 | 74.2-82.6 | 1500 in canonical | 60-75 | -5 to -20 | Coverage |

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
