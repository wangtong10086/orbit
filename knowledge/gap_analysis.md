# Gap Analysis

**Last updated**: 2026-03-19 (Strategist loop 48)
**Status**: v2 CANCELLED (data defects). v2.1 PLANNED — waiting for D8 NAVWORLD diversity (~132/400).

## Live Leaderboard (Block 7776573)

| Rank | Miner | GAME | NAVWORLD | SWE-SYNTH | LIVEWEB | LGC-v2 | PRINT | Weight |
|------|-------|------|----------|-----------|---------|--------|-------|--------|
| 1 | affshoot | 49.44 | 16.28 | 43.00 | 19.16 | 89.11 | 79.80 | 0.508 |
| 2 | vera6 | 50.56 | 22.52 | 30.00 | 19.44 | 90.40 | 82.56 | 0.254 |
| 3 | RLStepone | 48.73 | 20.34 | 38.00 | 15.93 | 87.60 | 80.81 | 0.127 |
| 4 | AnastasiaFantasy | 40.78 | 22.16 | 37.00 | 17.16 | 83.20 | 80.83 | 0.063 |
| 5 | EdmondMillion-19 | 45.55 | 20.69 | 38.00 | 14.57 | 86.80 | 81.73 | 0.032 |
| 6 | coffie3 | 40.26 | 20.72 | 42.00 | 16.86 | 83.61 | 74.19 | 0.016 |

**Leaderboard is volatile** — wisercat dropped from #1 in one block. Balance is key.

## 4-env GM Analysis

**Competitor 4-env GMs (GAME x NAVWORLD x SWE-SYNTH x LIVEWEB)**:
- affshoot #1: ~28.5
- vera6 #2: ~28.9
- RLStepone #3: ~28.4

Top 3 cluster around 28-29. NAVWORLD is the differentiator (affshoot weakest at 16.28).

## Gap Table (vs #1 affshoot)

| Env | #1 Score | Field Range | Our Data | Expected | Gap | Priority |
|-----|----------|-------------|----------|----------|-----|----------|
| GAME | 49.44 | 40-51 | 2916 | 25-35 | -14 to -24 | P1 |
| NAVWORLD | 16.28 | 16-24 | 2248+400 | 8-15 | -1 to -8 | **P0** |
| SWE-SYNTH | 43.00 | 30-43 | 983 | 10-25 | -18 to -33 | P1 |
| LIVEWEB | 19.16 | 15-19 | 18 | 15-20 | -4 to +1 | Maintain |
| LGC-v2 | 89.11 | 83-90 | excluded | 0 | N/A | Excluded |
| PRINT | 79.80 | 74-83 | excluded | 0 | N/A | Excluded |

LGC-v2/PRINT excluded from training per user directive (4-env only, all phases).

## v2.1 Data Plan

| Env | Count | Source |
|-----|-------|--------|
| GAME | ~3084 | 2916 canonical + 150 goofspiel + 18 leduc pending |
| NAVWORLD | ~2648 | 2248 + ~400 D8 Phase 1 diversity |
| SWE-SYNTH | 983 | canonical |
| LIVEWEB | 18 | canonical |
| **Total** | **~6733** | |

## ROI Analysis

| Action | Impact | Effort | ROI |
|--------|--------|--------|-----|
| D8 NAVWORLD diversity (+400, 8 query types) | Break 5-template ceiling | Medium | **Highest** |
| D7 gin_rummy merge (+275 HIGH) | Better gin_rummy learning | Done | Done |
| goofspiel/leduc merge (+168) | More learnable game data | Low | Medium |

## Action Items

- [x] D1-D7 complete
- [x] D10 schema fix (tool_calls flattened to tags)
- [x] D7 merge: 275 HIGH gin_rummy → canonical (GAME 2641→2916)
- [ ] **D8**: NAVWORLD Phase 1 diversity (132/400 done)
- [ ] **D11**: goofspiel 150 + leduc 18 merge + v2.1 data validation
- [ ] v2.1 training → eval → diagnose
- [ ] If GM <20 → v2.2 iteration
