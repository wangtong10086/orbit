# Affine Forge Playbook

## Goal

Affine Leaderboard (Bittensor Subnet 120) **#1**.

## Active Environments (4个)

**训练和优化**: GAME, NAVWORLD, SWE-SYNTH, LIVEWEB
**忽略**: LGC-v2, PRINT

## Scoring Mechanism

- **Subset scoring**: all environment combinations are evaluated
- **Geometric mean** within each subset — any zero kills that subset
- **Higher layers weight exponentially more**
- GAME scheduling weight 3.0 = sampled 3x more (more data points), NOT scored higher
- **NAVWORLD弱则全盘皆输** — GM最大瓶颈

## Current State

- Ranking: Not deployed
- Model: Qwen3-32B QLoRA SFT
- Machine: 4xH200 (576GB VRAM, 2.4T disk) — ONLINE
- **v2: RUNNING** — launched ~13:15 UTC, 243 steps, ETA ~19:15 UTC
- Data: GAME 2641 + NAVWORLD 2248 + SWE-SYNTH 983 + LIVEWEB 18 = **5890 samples**

## Training Data (v2)

| Env | Count | Notes |
|-----|-------|-------|
| GAME | 2641 | 7 active games, 75.1% learnable, includes bot data |
| NAVWORLD | 2248 | SFT plateau confirmed, DPO for Phase 3 |
| SWE-SYNTH | 983 | seq=8192 unlocks 49% complete entries |
| LIVEWEB | 18 | Safety net |
| **Total** | **5890** | |

## Competitor Landscape (LIVE — Block 7772891)

| Rank | Miner | GAME | NAVWORLD | SWE-SYNTH | LIVEWEB |
|------|-------|------|----------|-----------|---------|
| 1 | affshoot | 50.03 | 15.72 | 53.19 | 19.08 |
| 2 | vera6 | 50.59 | 25.12 | 27.00 | 19.11 |
| 3 | wisercat | 47.06 | 23.88 | 39.39 | 18.07 |
| 4 | AnastasiaFantasy | 40.84 | 24.84 | 40.00 | 16.53 |
| 5 | RLStepone | 49.37 | 21.88 | 39.00 | 16.31 |
| 6 | coffie3 | 41.56 | 21.69 | 46.00 | 16.38 |

## Priority Roadmap — 阶段迭代制

**规则**: 未达阶段目标 → 小版本迭代(v2a, v2b...)直到达标 → 才进入下一阶段

### Phase 2 (当前): 4-env基线 + GAME修复 — 目标: 上榜 + 4-env GM ≥20
- **v2**: GAME 2641 + seq=8192, 5890 samples
- **GAME目标**: ≥25
- **NAVWORLD目标**: ≥5 (确认SFT天花板)
- **SWE-SYNTH目标**: ≥10
- **LIVEWEB目标**: ≥15
- **GM目标**: 4-env GM ≥20
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
