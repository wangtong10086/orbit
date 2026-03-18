# Affine Forge Playbook

## Goal

Affine Leaderboard (Bittensor Subnet 120) **#1**.

## Active Leaderboard Environments (4个)

**只有4个环境参与评分**: GAME, NAVWORLD, SWE-SYNTH, LIVEWEB

**LGC-v2和PRINT不在活跃排行榜环境中** — 不训练、不评估。

## Scoring Mechanism

- **Subset scoring**: all environment combinations (L1-L4) are evaluated
- **Geometric mean** within each subset — any zero kills that subset
- **Higher layers weight exponentially more** — L4 (all 4 envs) has 8x weight of L1
- GAME scheduling weight 3.0 = sampled 3x more (more data points), NOT scored higher
- **4-env GM**: NAVWORLD弱则全盘皆输 — 5.7分时GM被严重拉低

## Current State

- Ranking: Not deployed
- Model: Qwen3-32B QLoRA SFT
- Machine: 4xH200 (576GB VRAM, 2.4T disk) — ONLINE
- **v2: APPROVED** — 4-env focused, GAME 2416 + seq=8192, total 5665 samples
- Data agent已生成147条gin_rummy bot数据，GAME总量2416

## Training Data (v2, 4 environments only)

| Env | Count | Notes |
|-----|-------|-------|
| GAME | 2416 | 7 active games, 72.8% learnable, +147 gin_rummy bot |
| NAVWORLD | 2248 | SFT plateau confirmed, DPO for Phase 3 |
| SWE-SYNTH | 983 | seq=8192解锁49%完整对话 |
| LIVEWEB | 18 | Safety net, v11~24已领先 |
| **Total** | **5665** | |

**不包含**: LGC-v2, PRINT (非活跃环境)

## Competitor Landscape (LIVE — Block 7771839, 4-env only)

| Rank | Miner | GAME | NAVWORLD | SWE-SYNTH | LIVEWEB | 4-env GM |
|------|-------|------|----------|-----------|---------|----------|
| 1 | affshoot | 50.75 | 16.75 | 56.84 | 19.36 | ~31.4 |
| 2 | AnastasiaFantasy | 41.63 | 24.56 | 39.00 | 16.08 | ~28.5 |
| 3 | vera6 | 50.48 | 24.05 | 25.00 | 18.95 | ~27.8 |
| 4 | RLStepone | 49.66 | 21.76 | 34.00 | 15.80 | ~28.0 |

## Priority Roadmap — 阶段迭代制

**规则**: 未达阶段目标 → 小版本迭代(v2a, v2b...)直到达标 → 才进入下一阶段

### Phase 2 (当前): 4-env基线 + GAME修复 — 目标: 上榜 + GM ≥20
- **v2**: GAME 2416 + seq=8192, 4-env only, 5665 samples
- **GAME目标**: ≥25分
- **NAVWORLD目标**: ≥5分 (确认SFT天花板)
- **SWE-SYNTH目标**: ≥10分 (seq=8192, 格式学习)
- **LIVEWEB目标**: ≥15分 (18条安全网)
- **GM目标**: ≥20 (上榜)
- 若GM<20 → v2a: 诊断最弱环境，针对性修复 → 迭代直到GM≥20

### Phase 3: DPO突破NAVWORLD — 目标: GM ≥28 (Top 4)
- NAVWORLD DPO (241对) — 5.7→15+ (突破SFT天花板)
- GAME DPO (589对) — 推高强项
- 若GM<28 → v3a: 调整DPO参数/数据 → 迭代

### Phase 4: 冲击Top 2 — 目标: GM ≥32
- SWE-SYNTH数据增量 + seq=16384
- GAME Zero-tier用DPO/RL
- LIVEWEB上游压缩 (需用户授权)
- 若GM<32 → 迭代

### Phase 5: 冲击 #1 — 目标: GM ≥35
- 全环境精细优化
- 数据配比A/B测试
- RL/MCTS for hard GAME games

## Rules Reference

Experiment protocol, loop flow, hard constraints, and key commands are in `CLAUDE.md` (single source of truth).
