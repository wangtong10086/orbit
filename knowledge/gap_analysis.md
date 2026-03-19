# Gap Analysis

**Last updated**: 2026-03-19 (Strategist loop 59)
**Status**: v2.1 RUNNING — step 61/287, loss 0.38 at step 50 (PASS). ETA ~12:15 UTC.

## Live Leaderboard (Block 7777474)

| Rank | Miner | GAME | NAVWORLD | SWE-SYNTH | LIVEWEB | LGC-v2 | PRINT | Weight |
|------|-------|------|----------|-----------|---------|--------|-------|--------|
| 1 | wisercat | 46.48 | 23.34 | 42.42 | 19.60 | 88.40 | 79.90 | 0.508 |
| 2 | affshoot | 49.58 | 16.31 | 43.43 | 19.18 | 90.00 | 79.59 | 0.254 |
| 3 | vera6 | 50.33 | 21.56 | 28.00 | 19.62 | 90.40 | 82.90 | 0.127 |
| 4 | RLStepone | 48.41 | 19.15 | 39.80 | 15.87 | 88.00 | 81.12 | 0.063 |
| 5 | AnastasiaFantasy | 40.76 | 21.41 | 37.00 | 16.63 | 83.20 | 81.15 | 0.032 |
| 6 | EdmondMillion | 46.03 | 20.12 | 40.00 | 14.81 | 87.20 | 82.14 | 0.016 |

**Extremely volatile**: wisercat dropped off entirely (Block 7776573), back at #1 (Block 7777474).

## 4-env GM Analysis

**Competitor 4-env GMs (GAME x NAVWORLD x SWE-SYNTH x LIVEWEB)**:
- wisercat #1: (46.48 x 23.34 x 42.42 x 19.60)^(1/4) ≈ 31.0
- affshoot #2: (49.58 x 16.31 x 43.43 x 19.18)^(1/4) ≈ 28.7
- vera6 #3: (50.33 x 21.56 x 28.00 x 19.62)^(1/4) ≈ 27.8

**wisercat leads by NAVWORLD** (23.34 vs field 16-22). NAVWORLD is THE differentiator.

## Gap Table (vs #1 wisercat)

| Env | #1 Score | Field Range | v2.1 Data | Expected | Gap | Priority |
|-----|----------|-------------|-----------|----------|-----|----------|
| GAME | 46.48 | 40-50 | 2916 | 25-35 | -11 to -21 | P1 |
| NAVWORLD | 23.34 | 16-23 | 2645 | 8-15 | -8 to -15 | **P0** |
| SWE-SYNTH | 42.42 | 28-43 | 983 | 10-25 | -17 to -32 | P1 |
| LIVEWEB | 19.60 | 15-20 | 347 | 15-20 | -5 to 0 | Maintain |
| LGC-v2 | 88.40 | 83-90 | excluded | 0 | N/A | Excluded |
| PRINT | 79.90 | 79-83 | excluded | 0 | N/A | Excluded |

## v2.1 Training Status

- Data: GAME 2916 + NAVWORLD 2645 + SWE-SYNTH 983 + LIVEWEB 347 = 6891
- Step 61/287, loss 0.38 at step 50 (healthy)
- ETA ~12:15 UTC

## Action Items

- [x] D7-D8-D10 all complete
- [x] v2.1 launched, training healthy
- [ ] v2.1 training completes → Trainer evals GAME+NAVWORLD 100s
- [ ] Analyze results → if GM<20 → v2.2
- [ ] goofspiel 150 + leduc 18 still pending merge (v2.2 if needed)
