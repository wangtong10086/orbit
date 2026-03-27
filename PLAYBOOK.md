# Affine Forge Playbook

## Goal

Affine Leaderboard (Bittensor Subnet 120) **#1**.

## Active Environments

**Training and optimization**: GAME, NAVWORLD, **SWE-Infinite**, LIVEWEB
**Excluded**: LGC-v2, PRINT (user directive)

## Scoring Mechanism

- **6 environments on leaderboard** — GAME, LGC-v2, LIVEWEB, NAVWORLD, PRINT, SWE-INFINITE
- **Geometric mean** within each subset — any zero kills that subset
- **Higher layers weight exponentially more** — L6 (all 6 envs) = 32x L1
- We cover 4/6 envs max. Missing LGC-v2 + PRINT caps at L4.

## Current State

**v2.26: TRAINING on m2** — started 05:56 UTC (tokenizing). Removed all liars_dice. 23962 entries.
**v2.27: DRAFTING** — v12 GAME (no think 16575) + LW v20+HN (10799) + SWE-I 1037. Total 32813. Awaiting user data confirmation + v2.26 eval.

**Best per env**: GAME 29.70 (v2.23), NW 42.84 (v2.21), **LW 27.76 (v2.25)**

## Training History (key versions)

| Version | GAME | NW | LW | Data | Key |
|---------|------|-----|-----|------|-----|
| v2.17a | 27.50 | **42.34** | 5.78 | 8401 | NW best (no parser) |
| v2.17b | **29.72** | 35.48 | 4.17 | 8775 | GAME best |
| v2.23 ckpt-550 | 29.70 | 34.88 | **17.68** | 24873 | LW best |
| v2.24 ckpt-500 | 24.40 | 19.57 | 12.69 | 20308 | ALL REGRESSED — buggy GAME v8 |
| **v2.25 ckpt-400** | 25.26 | **40.57** | **27.76** | 23783 | **LW NEW BEST**, NW recovered, liars=0% |

## Data Status (available for v2.27)

| Env | Count | File | Key Changes |
|-----|-------|------|-------------|
| GAME | 16575 | game_v12_rebalanced.jsonl | No think chains, liars call ratio fixed |
| NW | 4402 | navworld.jsonl | V6+V8 (same as v2.26) |
| LW | 10799 | liveweb.jsonl | v20+HN: 9999 base (no think) + 800 HN diversity (with think) |
| SWE-I | 1037 | swe_infinite.jsonl | +184 from v2.25 |
| **Total** | **32813** | | |

## Confirmed Rules (v2.18-v2.25)

1. **NO reasoning-parser qwen3** — A/B confirmed harmful
2. ~~**Checkpoint 80-85%**~~ — v2.25 optimal at 57%. Test multiple checkpoints.
3. **GAME data quality critical** — buggy data cross-contaminates all envs
4. **LW tools fix validated** — 17.68→27.76 (+57%)
5. **Final save corruption** — always merge from numbered checkpoint
6. **One variable at a time** — v2.25 changed 13 GAME vars, can't isolate liars regression

## Competitor Landscape (Block 7834920)

| Rank | Miner | GAME | NW | LW | SWE-I | Weight |
|------|-------|------|-----|-----|-------|--------|
| 1 | EdmondMillion | 46.22 | 32.81 | 18.69 | 8.25 | 0.508 |
| 2 | luis1027 | 48.22 | 20.07 | 17.90 | 4.82 | 0.254 |
| 3 | wisercat | 49.54 | 21.78 | 15.49 | 4.71 | 0.127 |
| **ours** | — | 29.70 | **42.84** | **27.76** | — | not submitted |

**We lead NW (+10 vs #1) and LW (+8 vs #1). GAME gap is -17 to -20. SWE-I untested.**

## Rules Reference

See `CLAUDE.md` for full rules.
