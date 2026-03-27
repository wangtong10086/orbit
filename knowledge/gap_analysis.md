# Gap Analysis

**Last updated**: 2026-03-27 05:30 UTC (Block 7834920)

## Best Scores & Competitive Position

| Env | Our Best | Model | #1 Competitor | Gap | Rank |
|-----|----------|-------|--------------|-----|------|
| GAME | 29.70 | v2.23 | 49.54 (wisercat) | -19.84 | last |
| **NW** | **42.84** | v2.21 | 32.81 (EdmondMillion) | **+10.03** | **#1** |
| **LW** | **27.76** | **v2.25** | 19.40 (deepresearch001) | **+8.36** | **#1** |
| SWE-I | never eval'd | — | 8.25 (EdmondMillion) | ? | ? |
| LGC-v2 | excluded | — | 93.83 | N/A | N/A |
| PRINT | excluded | — | 86.86 | N/A | N/A |

**Layer coverage**: 4/6 envs → max L4 subsets. L4 weight=48 vs competitors' L6 weight=192.
Missing LGC-v2 + PRINT = fundamental scoring cap.

## v2.26 Status — EVALUATING

v2.26 removed ALL liars_dice data (v10 liars not available on HF as v8 format).
Eval in progress: GAME ~53/100, NW 5/100, LW ~18/100.
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

## v2.27 Hypothesis: v11 GAME Data (No Think Chains)

v11 data: 17369 entries, NO think chains (bare action IDs), MCTS 1.5x eval bots.
This matches the **exact format** top miners use.

Expected impact:
- Scoring games (goof+leduc+gin+liars): maintain ~25-30 points
- Spatial games: **first chance to score non-zero** with correct format
- Even 5-10% on hex/othello/clobber = +3-6 GAME points
- NW/LW: maintain with proven data

## Confirmed Rules (updated v2.27)

1. **NO reasoning-parser** — A/B tested, hurts all envs
2. **Checkpoint ~50-60%** — v2.25 optimal at 57%. Test multiple checkpoints per run
3. **GAME data quality critical** — buggy data cross-contaminates all envs (v2.24)
4. **LW tools fix validated** — 17.68→27.76 (+57%)
5. **Final save corruption** — always merge from numbered checkpoint
6. **NW recovers with good GAME data** — v2.24 NW=19.57, v2.25 NW=40.57
7. **No think chains for GAME** — competitors use bare action IDs, v11 matches this
8. **One variable at a time** — v2.25 changed 13 vars, can't isolate regressions

## Priority Stack (ROI-ranked)

1. **GAME spatial games (hex/othello/clobber)** — 19+ point potential, biggest single gap
2. **SWE-I eval** — never tested, 1037 training entries ready, competitors score 4-9
3. **GAME liars_dice** — 3-4 point recovery from v2.23 levels
4. **Maintain NW/LW** — already #1, protect the lead
