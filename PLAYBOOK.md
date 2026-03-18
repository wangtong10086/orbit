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

- Ranking: Not deployed (fresh start from inherited data/knowledge)
- Model: Qwen3-32B QLoRA SFT (base → fine-tune)
- Inherited: 12,194 canonical entries across 7 environments
- Previous best (old repo v11): GAME 22.6, NAVWORLD 5.7
- New machine: awaiting user provision
- v1 experiment: designed (see `experiments/v1-baseline.yaml`), status=planned

## Training Environments (ALL 6 required for coverage)

**v1 trains on all 6 leaderboard environments.** Geometric mean demands full coverage — zero on any env kills all subsets containing it.

| Env | v1 Count | Status | Notes |
|-----|----------|--------|-------|
| NAVWORLD | 2248 | Active | SFT plateau confirmed. #1 lever for GM improvement. |
| GAME | 1415 | Active | Missing 4 strong-tier games. SFT ceiling ~40-50. |
| SWE-SYNTH | ~1017 | Cleaning | 334 think-tag entries being removed. 98% truncated at seq=4096. |
| LIVEWEB | 10 | Minimal | Only 10/430 entries fit seq=4096. Safety net only. |
| LGC-v2 | 1500 | Subsample | ~95 score, already topped. Maintain coverage. |
| PRINT | 1500 | Subsample | ~80 score, near top. Maintain coverage. |

**Total v1 data: ~7690 samples**

## Data Quality Issues (from Data Agent audit)

1. **SWE-SYNTH**: 24.7% think tag contamination — being cleaned (BLOCKER for v1)
2. **GAME**: missing 4 strong-tier games (hearts, bridge, blackjack, euchre) — v2 priority
3. **GAME**: missing `game` metadata field — tracking issue
4. **LIVEWEB**: 99.5% of data >16K chars — unusable at seq=4096
5. **Canonical files root-owned** — need `sudo chown` before modifications

## Blockers

1. **No machine** — awaiting user provision
2. **Forge CLI broken** — missing `click` module
3. **Data cleanup pending** — SWE-SYNTH think tags, LGC-v2/PRINT subsampling
4. **File permissions** — `data/canonical/` is root-owned

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

## Competitor Landscape (from breakthrough analysis)

| Env | #1 Score | #1 Miner | Our Target |
|-----|----------|----------|------------|
| GAME | 63.2 | RLStepone | 35-45 (SFT+DPO) |
| NAVWORLD | 33.7 | RLStepone | 20-30 (DPO) |
| SWE-SYNTH | ~44 | AnastasiaFantasy | 35-40 (seq=8192) |
| LIVEWEB | ~28 | ? | ~24 (maintain) |
| LGC-v2 | ~95 | ? | ~95 (maintain) |
| PRINT | ~86 | ? | ~82 (maintain) |

## Rules Reference

Experiment protocol, loop flow, hard constraints, and key commands are in `CLAUDE.md` (single source of truth). Training-specific reference values are in Trainer's ROLE.md.
