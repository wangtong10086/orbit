# Affine Forge Playbook

## Goal

Affine Leaderboard (Bittensor Subnet 120) **#1**.

## Active Environments

**Training**: GAME, NAVWORLD, SWE-Infinite, LIVEWEB, MEMORYGYM
**Excluded**: LGC-v2, PRINT (user directive)

## Scoring Mechanism

- **6 environments on leaderboard** — GAME, LGC-v2, LIVEWEB, NAVWORLD, PRINT, SWE-INFINITE
- **Geometric mean** within each subset — any zero kills that subset
- **Higher layers weight exponentially more** — L6 (all 6 envs) = 32x L1
- We cover 4/6 envs max. Missing LGC-v2 + PRINT caps at L4.

## Current State

**v2.28: COMPLETED** — Full FT Qwen3-32B, 155k data, stopped at step 2800/4846 (58%) due to overfitting.

### v2.28 Results — Full FT Breakthrough

| Checkpoint | GAME | NW | LW | SWE-I | Strategy |
|-----------|------|-----|-----|-------|----------|
| ckpt600 | 36.2 | **44.1** | 38.5 | 0.0 | NW best |
| **ckpt800** | **40.1** | 37.5 | 37.6 | 4.6 | GAME best |
| **ckpt1200** | 39.4 | 39.7 | 39.7 | 5.3 | **Most balanced** |
| ckpt2000 | 35.3 | 32.8 | **44.5** | **17.4** | LW/SWE best |

### vs QLoRA Best (v2.17-v2.25)

| Env | QLoRA Best | Full FT Best | Improvement |
|-----|-----------|-------------|-------------|
| GAME | 29.70 | **40.1** (ckpt800) | **+35%** |
| NW | 42.84 | **44.1** (ckpt600) | **+3%** |
| LW | 27.76 | **44.5** (ckpt2000) | **+60%** |
| SWE-I | never eval'd | **17.4** (ckpt2000) | **Beat competitor #1 (14.0)** |

### Key Breakthroughs
- **Hex 57.1%, Othello 28.6%** — spatial games scored for first time ever (was 0% across all QLoRA versions)
- **SWE-I 17.4** — exceeds EdmondMillion's 14.0 (#1 competitor)
- **Full FT >> QLoRA** confirmed: 380x parameter capacity unlocked spatial game learning

### Key Issue: Overfitting from Data Imbalance
- GAME was 67% of training data → GAME/NW peak at ckpt800-1200, then degrade
- LW/SWE keep improving with more training (smaller data proportion benefits from longer training)
- v2.29 must rebalance: GAME 67%→~40%, increase NW/SWE

## Submission Candidates

| Candidate | GAME | NW | LW | SWE-I | Geo Mean (4 env) |
|-----------|------|-----|-----|-------|-------------------|
| ckpt800 | **40.1** | 37.5 | 37.6 | 4.6 | ~23.5 |
| **ckpt1200** | 39.4 | 39.7 | 39.7 | 5.3 | **~24.8** |
| ckpt2000 | 35.3 | 32.8 | 44.5 | 17.4 | ~30.6 |

ckpt2000 has highest geo mean due to SWE-I 17.4 (non-zero in all 4 envs).

## Data Status

### v2.28 Training Data (155k)

| Env | Count | % |
|-----|-------|---|
| GAME | 103592 | 67% |
| MemoryGym | 20000 | 13% |
| LW | 19776 | 13% |
| NW | 10006 | 6% |
| SWE-I | 1735 | 1% |
| **Total** | **155109** | |

### v2.29 Planned Data (rebalanced by data-game)

| Env | v2.28 | v2.29 | Change |
|-----|-------|-------|--------|
| GAME | 103592 | **59000** | -44% (cut saturated games) |
| NW | 10006 | TBD | increase |
| LW | 19776 | TBD | maintain |
| SWE-I | 1735 | TBD | increase |
| MemoryGym | 20000 | TBD | maintain |

### Per-Game Analysis (v2.28 ckpt1200)

| Game | Data | Score | vs QLoRA | Status |
|------|------|-------|----------|--------|
| goofspiel | 10k→3k | 86.7% | = | Saturated |
| hex | 15k | **57.1%** | +57.1 | **BREAKTHROUGH** |
| gin_rummy | 9k→8k | 49.4% | +6.8 | Improved |
| othello | 13k | **28.6%** | +28.6 | **BREAKTHROUGH** |
| leduc_poker | 9.5k→5k | 38.9% | -16.3 | Regressed (dilution) |
| liars_dice | 19k→5k | 6.7% | -13.3 | Regressed (dilution) |
| clobber | 28k→10k | 7.1% | +7.1 | SFT ceiling |

## Competitor Landscape (Block 7837772)

| Rank | Miner | GAME | NW | LW | SWE-I | Weight |
|------|-------|------|-----|-----|-------|--------|
| 1 | EdmondMillion | 46.25 | 33.50 | 18.86 | 14.00 | 0.508 |
| 2 | luis1027 | 46.82 | 22.80 | 17.61 | 8.24 | 0.254 |
| 3 | vera6 | 47.05 | 22.85 | 18.41 | 8.00 | 0.127 |
| 4 | RLStepone/h15 | 46.61 | 35.32 | 28.42 | 4.04 | 0.063 |
| **ours (ckpt1200)** | — | **39.4** | **39.7** | **39.7** | 5.3 | not submitted |

**We now lead NW and LW again. GAME gap narrowed from -17 to -7. SWE-I competitive.**

## Confirmed Rules

1. **Full FT > QLoRA** — 380x parameter capacity, spatial games breakthrough
2. **ms-swift** — correct loss masking, tool calls, chat template
3. **NO reasoning-parser** — A/B tested, hurts all envs
4. **seq=32k** — 80% of LW was truncated at 8k
5. **No think chains for GAME** — bare action IDs
6. **Never upload HF during training** — caused m3 crash
7. **Data balance critical** — GAME 67% caused overfitting at ckpt1200+
8. **epochs=1 only** — overfits catastrophically
9. **Early stopping by env** — different envs peak at different checkpoints

## Rules Reference

See `CLAUDE.md` for full rules.
