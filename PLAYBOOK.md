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
- Model: Qwen3-32B QLoRA SFT (base -> fine-tune)
- Inherited: 12,194 canonical entries across 7 environments
- Previous best (old repo v11): GAME 22.6, NAVWORLD 5.7
- New machine: awaiting user provision

## Focus Environments

Current focus: **GAME, NAVWORLD, SWE-SYNTH, LIVEWEB**.

| Env | Count | Status |
|-----|-------|--------|
| NAVWORLD | 2248 | Active, SFT plateau detected |
| GAME | 1415 | Active, structural ceiling on hard games |
| SWE-SYNTH | 1351 | Active, needs seq=8192 |
| LIVEWEB | 430 | Active, data too long |

Other data available: LGC-v2 (3353), PRINT (2898), MemoryGym (499).

## Audit Findings (from 12 prior iterations)

See `knowledge/audit_report.md` for full analysis. Key takeaways:

1. **SFT plateau on NAVWORLD**: 3.4x data -> only 12% gain. DPO/RL needed.
2. **GAME structural ceiling**: othello/hex/liars_dice always 0% via SFT. ~40-50pt ceiling.
3. **No controlled experiments**: every version changed 2-5 variables simultaneously.
4. **No regression testing**: SWE-SYNTH/LIVEWEB never locally evaluated.
5. **DPO pipeline unused**: 2688 pairs built 6 days ago, never tested.

## Priority (by ROI)

1. **v1 baseline** — train with 4-env data (GAME+NAVWORLD+SWE-SYNTH+LIVEWEB), validate pipeline
2. **Full eval** — GAME + NAVWORLD minimum 100 samples each, establish baseline
3. **DPO experiment** — test on NAVWORLD/GAME (SFT clearly plateauing)
4. **DDB refresh** — data >24h stale, new high-score samples for all 4 envs
5. **SWE-SYNTH seq=8192** — untested approach from v12
6. **NAVWORLD rejection sampling** — use scorer to filter existing data, keep only high-quality

## Rules Reference

Experiment protocol, loop flow, hard constraints, and key commands are in `CLAUDE.md` (single source of truth). Training-specific reference values are in Trainer's ROLE.md.
