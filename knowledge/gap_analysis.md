# Gap Analysis

**Last updated**: 2026-03-30 05:00 UTC

## Best Scores — v2.28 Full FT

| Env | Our Best | Checkpoint | #1 Competitor | Gap | Rank |
|-----|----------|-----------|--------------|-----|------|
| GAME | **40.1** | ckpt800 | 49.03 (wisercat) | -8.9 | improving |
| **NW** | **44.1** | ckpt600 | 39.12 (Sanguineey) | **+5.0** | **#1** |
| **LW** | **44.5** | ckpt2000 | 28.42 (RLStepone) | **+16.1** | **#1** |
| **SWE-I** | **17.4** | ckpt2000 | 14.00 (EdmondMillion) | **+3.4** | **#1** |

**We lead 3 of 4 trained envs. GAME gap narrowed from -19 to -9.**

## v2.28 Overfitting Analysis

| Checkpoint | GAME | NW | LW | SWE-I | Phase |
|-----------|------|-----|-----|-------|-------|
| ckpt600 | 36.2 | **44.1** | 38.5 | 0.0 | Early — NW peak |
| ckpt800 | **40.1** | 37.5 | 37.6 | 4.6 | GAME peak |
| ckpt1200 | 39.4 | 39.7 | 39.7 | 5.3 | Balanced |
| ckpt2000 | 35.3 | 32.8 | **44.5** | **17.4** | Overfitting GAME/NW, LW/SWE still improving |

**Root cause**: GAME 67% of data → model memorizes GAME early, then overfits. NW (6%) peaks early too. LW/SWE (14% combined) benefit from longer training.

## Spatial Games Breakthrough

| Game | QLoRA (all versions) | Full FT (ckpt1200) |
|------|---------------------|-------------------|
| hex | 0% | **57.1%** |
| othello | 0% | **28.6%** |
| clobber | 0% | **7.1%** |

Full FT's 380x parameter capacity unlocked spatial game learning that QLoRA could never achieve.

## GAME Per-Game Regressions

| Game | QLoRA Best | Full FT (ckpt1200) | Cause |
|------|-----------|-------------------|-------|
| leduc_poker | 55.2% | 38.9% | Data dilution (9.5k in 103k pool) |
| liars_dice | 20.0% | 6.7% | Data dilution (19k in 103k pool) |

Fix: reduce GAME total, increase leduc/liars proportion. data-game v18 rebalance addresses this.

## v2.29 Strategy

1. **Rebalance data**: GAME 67%→~40% (59k), increase NW/SWE
2. **Target**: GAME 42-45 (recover leduc/liars + maintain spatial), NW 44+, LW 40+, SWE-I 10+
3. **Early stopping**: eval at ckpt600, 800, 1000, 1200 — stop when GAME/NW decline

## Priority Stack

1. **Rebalance + v2.29 training** — fix data imbalance, recover leduc/liars
2. **Submit best checkpoint** — ckpt1200 or ckpt2000 for leaderboard ranking
3. **Expand SWE-I data** — 17.4 with 1735 entries, more data = higher score
4. **NW data expansion** — 10006→15000+ to sustain NW #1
