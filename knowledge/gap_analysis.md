# Gap Analysis

**Last updated**: 2026-03-27 12:00 UTC (Block 7837772)

## Best Scores & Competitive Position

| Env | Our Best | Model | #1 Competitor | Gap | Rank |
|-----|----------|-------|--------------|-----|------|
| GAME | 29.70 | v2.23 | 49.03 (wisercat) | -19.33 | last |
| NW | **42.84** | v2.21 | 39.12 (Sanguineey) | **+3.72** | **#1 shrinking** |
| LW | 27.76 | v2.25 | **28.42 (RLStepone)** | **-0.66 LOST #1** | **#2** |
| SWE-I | never eval'd | — | **14.00 (EdmondMillion)** | ? | ? |
| LGC-v2 | excluded | — | 93.83 | N/A | N/A |
| PRINT | excluded | — | 86.86 | N/A | N/A |

**Layer coverage**: 4/6 envs → max L4 subsets. L4 weight=48 vs competitors' L6 weight=192.
Missing LGC-v2 + PRINT = fundamental scoring cap.

## v2.26 Status — TRAINING on m2

v2.26 removed ALL liars_dice data. Training started m2 05:56 UTC (still tokenizing 23962 entries).
NOTE: Initial m1 run used WRONG data (v2.22). Trainer caught and relaunched on m2 with correct data.
m1 evals still running are from wrong model — DISCARD those results.
Variable: liars_dice removal. Hypothesis: if other games improve, liars data was cross-contaminating.

## Critical Strategic Insight: Competitor Format

**Top miners use NO think chains** — assistant outputs bare action ID (2-4 tokens, 0 reasoning_tokens).
All top miners share the same SFT lineage (identical action sequences on same tasks).

Top miner per-game breakdown (UID 94, ~48% total):
| Game | Win Rate | Our Best | Gap |
|------|----------|----------|-----|
| goofspiel | 82.9% | 90.91% | **+8.0** (we lead) |
| hex | **67.0%** | 0% | **-67.0** |
| gin_rummy | 54.2% | 36.42% | -17.8 |
| leduc_poker | 46.2% | 48.40% | +2.2 (we lead) |
| othello | **47.7%** | 0% | **-47.7** |
| liars_dice | 29.1% | 20.0% (v2.23) | -9.1 |
| clobber | **18.3%** | 0% | **-18.3** |

**Spatial games (hex+othello+clobber) account for ~19 GAME points** that we score 0% on.

## v2.27 Hypothesis: v12 GAME Data (No Think Chains + Liars Fix)

v12 rebalanced: 16575 entries, NO think chains, liars_dice call ratio fixed (41.7%→13%).
LW v20: 9999 entries, NO think chains (verified 0/9999 — v2.25's 27.76 was pure tool_call). Total: 32013.

Expected impact:
- Liars_dice: recover from 0% to ~15-20% (call ratio matches v8)
- Scoring games: maintain ~25-30 points (format change to bare IDs)
- Spatial games: possible breakthrough with no-think format (matches competitors)
- NW/LW: maintain with same data

Known GAME limitations (not blocking):
- gin_rummy: only 2.3% knock actions → model doesn't knock (needs pyspiel regen)
- leduc_poker: 0% fold in data → model over-passive (needs fold examples)
- spatial games: may still be SFT-unlearnable (0% across 3+ versions)

## Confirmed Rules (updated v2.27)

1. **NO reasoning-parser** — A/B tested, hurts all envs
2. **Checkpoint ~50-60%** — v2.25 optimal at 57%. Test multiple checkpoints per run
3. **GAME data quality critical** — buggy data cross-contaminates all envs (v2.24)
4. **LW tools fix validated** — 17.68→27.76 (+57%). No think chains in data (0/9999). Pure tool_call format.
5. **Final save corruption** — always merge from numbered checkpoint
6. **NW recovers with good GAME data** — v2.24 NW=19.57, v2.25 NW=40.57
7. **No think chains for GAME** — competitors use bare action IDs, v11 matches this
8. **One variable at a time** — v2.25 changed 13 vars, can't isolate regressions

## Priority Stack (ROI-ranked)

1. **GAME spatial games (hex/othello/clobber)** — 19+ point potential, biggest single gap
2. **SWE-I eval** — never tested, 1037 training entries ready, competitors score 4-9
3. **GAME liars_dice** — 3-4 point recovery from v2.23 levels
4. **Maintain NW/LW** — already #1, protect the lead
