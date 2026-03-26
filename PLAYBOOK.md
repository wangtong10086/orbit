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

**v2.25: COMPLETE** — GAME 25.26, NW 40.57, **LW 27.76 NEW BEST**. ckpt-400 (57%).

**Best per env**: GAME 29.70 (v2.23), NW 42.84 (v2.21), **LW 27.76 (v2.25)**

## Training History (key versions)

| Version | GAME | NW | LW | Data | Key |
|---------|------|-----|-----|------|-----|
| v2.17a | 27.50 | **42.34** | 5.78 | 8401 | NW best (no parser) |
| v2.17b | **29.72** | 35.48 | 4.17 | 8775 | GAME best |
| v2.23 ckpt-550 | 29.70 | 34.88 | **17.68** | 24873 | LW best |
| v2.24 ckpt-500 | 24.40 | 19.57 | 12.69 | 20308 | ALL REGRESSED — buggy GAME v8 |
| **v2.25 ckpt-400** | 25.26 | **40.57** | **27.76** | 23783 | **LW NEW BEST**, NW recovered, liars=0% |

## Data Status (v2.25 — training)

| Env | Count | % of mix | Notes |
|-----|-------|----------|-------|
| GAME | 9966 | 41.9% | v10: rule-based think, 13 bug fixes, gin_rummy 1000 |
| NW | 4148 | 17.4% | V6+V8 |
| LW | 8816 | 37.1% | Tools fix, goto+stop (by design) |
| SWE-I | 853 | 3.6% | |
| **Total** | **23783** | | |

## Confirmed Rules (v2.18-v2.25)

1. **NO reasoning-parser qwen3** — A/B confirmed harmful
2. ~~**Checkpoint 80-85%**~~ — v2.25 optimal at 57%. Test multiple checkpoints.
3. **GAME data quality critical** — buggy data cross-contaminates all envs
4. **LW tools fix validated** — 17.68→27.76 (+57%)
5. **Final save corruption** — always merge from numbered checkpoint
6. **One variable at a time** — v2.25 changed 13 GAME vars, can't isolate liars regression

## Competitor Landscape (Block 7827246)

| Rank | Miner | GAME | NW | LW | SWE-I |
|------|-------|------|-----|-----|-------|
| 1 | luis1027 | 48.58 | 22.43 | 19.35 | 7.45 |
| 2 | EdmondMillion | 47.69 | 34.86 | 17.71 | 9.18 |
| 4 | wisercat | 50.18 | 22.83 | 16.69 | 7.14 |
| **ours** | — | 29.70 | **42.84** | 17.68 | — |

## Rules Reference

See `CLAUDE.md` for full rules.
