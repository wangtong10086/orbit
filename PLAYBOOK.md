# Affine Forge Playbook

## Goal

Affine Leaderboard (Bittensor Subnet 120) **#1**.

## Scoring Mechanism (critical to understand)

- **Subset scoring**: all environment combinations (L1=single, L2=pairs, L3=triples...) are evaluated
- **Geometric mean** within each subset — any zero kills that subset
- **Higher layers weight exponentially more** (`weight = n * base^(layer-1)`, base=2)
- **Implication**: covering ALL environments > excelling at one. A miner scoring 20 across 6 envs beats one scoring 80 on 3 envs.
- GAME's scheduling weight 3.0 means it's **sampled 3x more** (more data points), NOT scored 3x higher
- All environments contribute equally to the geometric mean

## Current State

- Ranking: Not deployed (pre-v1)
- Model: Qwen3-32B QLoRA SFT (base → fine-tune)
- Machine: 4xH200 (576GB VRAM, 2.4T disk) — ONLINE
- Forge CLI: FIXED (deps in venv)
- v1 experiment: **APPROVED** (loop 3), status=approved, awaiting Trainer launch
- Data: all canonical files cleaned and in place (7664 samples verified)
- Previous best (old repo v11): GAME 22.6, NAVWORLD 5.7

## Training Environments (ALL 6 required for coverage)

**v1 trains on all 6 leaderboard environments.** Geometric mean demands full coverage — zero on any env kills all subsets containing it.

| Env | v1 Count | Status | Notes |
|-----|----------|--------|-------|
| NAVWORLD | 2248 | Active | SFT plateau confirmed. #1 lever for GM improvement. |
| GAME | 1415 | Active | Missing 4 strong-tier games. SFT ceiling ~40-50. |
| SWE-SYNTH | 983 | Cleaned | Think tags removed (verified count 983). 98% truncated at seq=4096. |
| LIVEWEB | 18 | Minimal | Only 18/430 entries <16K chars. Safety net only. |
| LGC-v2 | 1500 | Subsample | ~95 score, already topped. Maintain coverage. |
| PRINT | 1500 | Subsample | ~80 score, near top. Maintain coverage. |

**Total v1 data: ~7664 samples (verified)**

## Data Quality Issues

1. ~~**SWE-SYNTH think tags**~~ — RESOLVED: 368 contaminated entries removed, 983 clean in canonical
2. **GAME**: missing 4 strong-tier games (hearts, bridge, blackjack, euchre) — v2 priority
3. **GAME**: missing `game` metadata field — needed for per-game analysis
4. **LIVEWEB**: 99.5% of data >16K chars — only 18 usable at seq=4096
5. ~~**Canonical files root-owned**~~ — RESOLVED: Data agent used directory-level workaround

## Blockers

1. ~~**No machine**~~ — RESOLVED: 4xH200 online
2. ~~**Forge CLI broken**~~ — RESOLVED: deps installed in venv
3. ~~**Data cleanup pending**~~ — RESOLVED: canonical files replaced with cleaned/subsampled versions
4. ~~**File permissions**~~ — RESOLVED: all canonical files now claudeuser-owned (HF redownload)
5. ~~**Strategist approval**~~ — RESOLVED: v1 status=**approved** (loop 3)

## Priority Roadmap (by GM ROI)

### v1: Pipeline Baseline (~7690 samples, 6 envs)
- Validate full pipeline end-to-end
- Establish baseline scores for GAME + NAVWORLD (100+ samples each)
- Deploy → get on-chain scores for all 6 envs

### v2: NAVWORLD Quality + SWE-SYNTH seq=8192
- NAVWORLD rejection sampling (quality filter 2248 → ~800 high-quality)
- SWE-SYNTH seq=8192 training (unlocks 46% data vs 2.4% at seq=4096)
- GAME: add hearts/bridge/blackjack/euchre bot data

### v3: DPO Breakthrough
- DPO on NAVWORLD (241 pairs) — break SFT plateau (5.7 → 20+ target)
- DPO on GAME (589 pairs) — push past SFT ceiling

### v4+: Advanced
- LIVEWEB upstream compression (if user authorizes)
- GAME RL/MCTS for hard games (othello, hex, liars_dice)
- Data mix optimization (A/B testing ratios)

## Competitor Landscape (LIVE — Block 7771839, 2026-03-18)

| Rank | Miner | GAME | NAVWORLD | SWE-SYNTH | LIVEWEB | LGC-v2 | PRINT |
|------|-------|------|----------|-----------|---------|--------|-------|
| 1 | affshoot | 50.75 | 16.75 | 56.84 | 19.36 | 89.88 | 77.49 |
| 2 | AnastasiaFantasy | 41.63 | 24.56 | 39.00 | 16.08 | 81.53 | 80.42 |
| 3 | vera6 | 50.48 | 24.05 | 25.00 | 18.95 | 90.69 | 81.38 |
| 4 | RLStepone | 49.66 | 21.76 | 34.00 | 15.80 | 88.26 | 79.29 |

**Best per env**: GAME=affshoot 50.75, NAVWORLD=AnastasiaFantasy 24.56, SWE-SYNTH=affshoot 56.84 (deepresearch001 ~60.61), LIVEWEB=affshoot 19.36, LGC-v2=vera6 90.69, PRINT=vera6 81.38

| Env | Best Score | Our Target |
|-----|-----------|------------|
| GAME | 50.75 | 35-45 (SFT, v1 baseline 20-25) |
| NAVWORLD | 24.56 | 15-20 (SFT baseline, DPO for v3) |
| SWE-SYNTH | 56.84 | 35-40 (seq=8192 in v2) |
| LIVEWEB | 19.36 | ~24 (already competitive from v11) |
| LGC-v2 | 90.69 | ~95 (already competitive) |
| PRINT | 81.38 | ~82 (already competitive) |

## Rules Reference

Experiment protocol, loop flow, hard constraints, and key commands are in `CLAUDE.md` (single source of truth). Training-specific reference values are in Trainer's ROLE.md.
