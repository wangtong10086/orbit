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

## Inherited Data

| Env | Count | Share | Status |
|-----|-------|-------|--------|
| LGC-v2 | 3353 | 27.5% | Frozen (may be removed) |
| PRINT | 2898 | 23.8% | Frozen (may be removed) |
| NAVWORLD | 2248 | 18.4% | Active, SFT plateau detected |
| GAME | 1415 | 11.6% | Active, structural ceiling on hard games |
| SWE-SYNTH | 1351 | 11.1% | Active, needs seq=8192 |
| MemoryGym | 499 | 4.1% | Not yet on leaderboard |
| LIVEWEB | 430 | 3.5% | Active, data too long |

## Audit Findings (from 12 prior iterations)

See `knowledge/audit_report.md` for full analysis. Key takeaways:

1. **SFT plateau on NAVWORLD**: 3.4x data -> only 12% gain. DPO/RL needed.
2. **GAME structural ceiling**: othello/hex/liars_dice always 0% via SFT. ~40-50pt ceiling.
3. **No controlled experiments**: every version changed 2-5 variables simultaneously.
4. **No regression testing**: SWE-SYNTH/LIVEWEB never locally evaluated.
5. **Data mix not optimized**: 51% of data is LGC-v2+PRINT (potentially deprecated).
6. **DPO pipeline unused**: 2688 pairs built 6 days ago, never tested.

## Priority (by ROI)

1. **v1 baseline** — train with inherited data, validate pipeline on new machine
2. **Full eval** — GAME + NAVWORLD minimum 100 samples each, establish baseline
3. **DPO experiment** — test on NAVWORLD/GAME (SFT clearly plateauing)
4. **Data rebalance** — reduce LGC-v2/PRINT share, boost weak envs proportionally
5. **DDB refresh** — data >24h stale
6. **SWE-SYNTH seq=8192** — untested approach from v12

## Rules Reference

Experiment protocol, loop flow, hard constraints, and key commands are in `CLAUDE.md` (single source of truth). Training-specific reference values are in Trainer's ROLE.md.
