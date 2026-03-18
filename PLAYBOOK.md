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
- v1 experiment: superseded by v2 (v1 data incomplete — GAME只有1415条)
- **v2 experiment: APPROVED** — GAME 2660条 + seq=8192, 8909 total samples
- Data: GAME canonical updated to 2660 entries (recovered v7_clean from HF)
- Previous best (old repo v11): GAME 22.6, NAVWORLD 5.7

## Training Environments (ALL 6 required for coverage)

**v1 trains on all 6 leaderboard environments.** Geometric mean demands full coverage — zero on any env kills all subsets containing it.

| Env | v2 Count | v1 Count | Change | Notes |
|-----|----------|----------|--------|-------|
| GAME | **2269** | 1415 | **+60%** | 恢复v7_clean, 仅7个eval-active游戏. goofspiel 921, leduc_poker 332 |
| NAVWORLD | 2248 | 2248 | same | SFT plateau confirmed. DPO in v3. |
| SWE-SYNTH | 983 | 983 | same | seq=8192解锁49%完整对话 (vs 3.1% at 4096) |
| LIVEWEB | 18 | 18 | same | Safety net. 我们已领先竞品. |
| LGC-v2 | 1500 | 1500 | same | Maintain coverage. |
| PRINT | 1500 | 1500 | same | Maintain coverage. |

**Total v2 data: 8518 samples (+854 from v1)**

**GAME eval只测试7个游戏** (source: affine-cortex system_config.json, dataset_range [[0,500M],[600M,800M]]):
goofspiel(0), liars_dice(1), leduc_poker(2), gin_rummy(3), othello(4), hex(6), clobber(7).
blackjack/euchre/hearts/bridge **不在eval范围内**。

## Data Quality Issues

1. ~~**SWE-SYNTH think tags**~~ — RESOLVED
2. ~~**GAME数据不足**~~ — RESOLVED: 从HF恢复854条v7_clean数据，1415→2269
3. **GAME 29%数据是SFT无法学习的游戏** — 从47%降到29%（恢复后learnable占71%）
4. **GAME eval只测7个游戏** — blackjack/euchre/hearts/bridge不在范围内（已从canonical移除）
5. **SWE-SYNTH**: 97%数据在seq=4096被截断（只有32条完整）— v2用seq=8192修复
6. **LIVEWEB**: 结构性问题（中位70K chars），18条安全网够用
7. ~~**GAME metadata**~~ — RESOLVED
8. ~~**Canonical files root-owned**~~ — RESOLVED

## Blockers

1. ~~**No machine**~~ — RESOLVED: 4xH200 online
2. ~~**Forge CLI broken**~~ — RESOLVED: deps installed in venv
3. ~~**Data cleanup pending**~~ — RESOLVED: canonical files replaced with cleaned/subsampled versions
4. ~~**File permissions**~~ — RESOLVED: all canonical files now claudeuser-owned (HF redownload)
5. ~~**Strategist approval**~~ — RESOLVED: v1 status=**approved** (loop 3)

## Priority Roadmap — 每阶段目标清晰

### Phase 1 (v1): Pipeline Baseline — 目标: 上榜 + 建立基线
- **成功标准**: 6个环境全部非零分，部署上链
- **GAME目标**: ≥15分 (DDB-only可能低于v11的22.6)
- **NAVWORLD目标**: ≥5分 (确认SFT天花板)
- **LGC-v2/PRINT**: ≥80/≥70 (维持覆盖)
- **GM目标**: ≥25 (上榜，排名不重要)
- **状态**: 🟢 训练中，307步 ~4.25h

### Phase 2 (v2): GAME修复 + SWE-SYNTH解锁 — 目标: 接近Top 4
- **核心改动**: seq=8192 + 恢复600条GAME bot策略 + Zero-tier降采样
- **GAME目标**: 30-40分 (从v1基线+10-15, bot数据是关键)
- **SWE-SYNTH目标**: 25-35分 (seq=8192解锁49%完整对话)
- **GM目标**: ≥35 (接近vera6的~38 GM)
- **阻塞**: Data agent生成bot数据 + 确认game_bot_gen.py不依赖affinetes
- **预算**: ~$18

### Phase 3 (v3): DPO突破弱项 — 目标: Top 2
- **核心改动**: NAVWORLD DPO (241对) + GAME DPO (589对)
- **NAVWORLD目标**: 15-25分 (突破SFT天花板5.7→15+)
- **GAME目标**: 40-50分 (接近affshoot 50.75)
- **GM目标**: ≥40 (挑战#2 AnastasiaFantasy)

### Phase 4 (v4+): 冲击 #1
- LIVEWEB上游压缩 (需用户授权改affinetes源码)
- GAME RL/MCTS for zero-tier games (othello, hex)
- 数据配比A/B测试
- **GM目标**: ≥43 (超越affshoot)

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
