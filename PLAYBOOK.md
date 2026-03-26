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

**v2.25: TRAINING** — GAME v10 9966 + NW 4148 + LW 8816 + SWE-I 853 = 23783.

**Best per env**: GAME 29.70 (v2.23), NW 42.84 (v2.21), LW 17.68 (v2.23)

## Training History (key versions)

| Version | GAME | NW | LW | Data | Key |
|---------|------|-----|-----|------|-----|
| v2.17a | 27.50 | **42.34** | 5.78 | 8401 | NW best (no parser) |
| v2.17b | **29.72** | 35.48 | 4.17 | 8775 | GAME best |
| v2.23 ckpt-550 | 29.70 | 34.88 | **17.68** | 24873 | LW best, NW diluted by LW 12054 |
| **v2.24** | ? | ? | ? | 23778 | GAME v10 + gin_rummy 1000, LW tools fix |

## Data Status (v2.24)

| Env | Count | % of mix | Notes |
|-----|-------|----------|-------|
| GAME | 9966 | 41.9% | v10: rule-based think, gin_rummy 1000 |
| NW | 4148 | 17.4% | V6+V8 |
| LW | 8816 | 37.1% | Tools fix, goto+stop (by design) |
| SWE-I | 848 | 3.6% | |
| **Total** | **23778** | | |

## Confirmed Rules (v2.18-v2.23)

1. **NO reasoning-parser qwen3** — A/B confirmed harmful (all envs drop)
2. **Checkpoint ~80-85%** — late training overfits (3-6 point drop)
3. **NW needs ≥19% of mix** — below this, NW collapses
4. **LW single-turn format works** — 5.78→17.68 without parser
5. **GAME SFT ceiling ~30** — hex/othello/clobber = 0%, need better data (rule-based think, v9)
6. **Final save corruption** — always merge from numbered checkpoint

## Competitor Landscape (Block 7827246)

| Rank | Miner | GAME | NW | LW | SWE-I |
|------|-------|------|-----|-----|-------|
| 1 | luis1027 | 48.58 | 22.43 | 19.35 | 7.45 |
| 2 | EdmondMillion | 47.69 | 34.86 | 17.71 | 9.18 |
| 4 | wisercat | 50.18 | 22.83 | 16.69 | 7.14 |
| **ours** | — | 29.70 | **42.84** | 17.68 | — |

## Rules Reference

See `CLAUDE.md` for full rules.
