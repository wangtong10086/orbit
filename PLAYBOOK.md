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

**v2.26: ABANDONED** — m2 training crashed step 72/1146. Superseded by v2.27 full FT.
**v2.27: READY on m3** — Full FT Qwen3-32B + seq=32k + no think. 32813 entries. Awaiting user data confirmation.

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

## Competitor Landscape (Block 7837772)

| Rank | Miner | GAME | NW | LW | SWE-I | Weight |
|------|-------|------|-----|-----|-------|--------|
| 1 | EdmondMillion | 46.25 | 33.50 | 18.86 | **14.00** | 0.508 |
| 2 | luis1027 | 46.82 | 22.80 | 17.61 | 8.24 | 0.254 |
| 3 | vera6 | 47.05 | 22.85 | 18.41 | 8.00 | 0.127 |
| **4** | **RLStepone/h15** | **46.61** | **35.32** | **28.42** | 4.04 | 0.063 |
| 10 | Sanguineey | 44.52 | **39.12** | 19.68 | 6.59 | 0.000 |
| **ours** | — | 29.70 | **42.84** | 27.76 | — | not submitted |

**LW #1 lost to RLStepone (28.42 vs 27.76). NW lead shrinking (Sanguineey 39.12). GAME gap -17 to -19. Urgency: HIGH.**

## Rules Reference

See `CLAUDE.md` for full rules.
