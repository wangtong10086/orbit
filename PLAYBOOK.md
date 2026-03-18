# Affine Forge Playbook

## Goal

Affine Leaderboard (Bittensor Subnet 120) **#1**.

## Leaderboard Environments (6个)

**Scoring uses ALL 6 environments**: GAME, LGC-v2, LIVEWEB, NAVWORLD, PRINT, SWE-SYNTH

**Strategy**: Focus training effort on GAME, NAVWORLD, SWE-SYNTH, LIVEWEB. LGC-v2/PRINT: maintain coverage only (user directive — don't optimize, include minimal data to prevent degradation).

## Scoring Mechanism

- **Subset scoring**: all environment combinations (L1-L6) are evaluated
- **Geometric mean** within each subset — any zero kills that subset
- **Higher layers weight exponentially more** — L6 (all 6 envs) has 32x weight of L1
- GAME scheduling weight 3.0 = sampled 3x more (more data points), NOT scored higher
- **NAVWORLD弱则全盘皆输** — and LGC-v2/PRINT coverage is essential for L5/L6

## Current State

- Ranking: Not deployed
- Model: Qwen3-32B QLoRA SFT
- Machine: 4xH200 (576GB VRAM, 2.4T disk) — ONLINE
- **v2: RUNNING** — launched ~13:15 UTC, 243 steps, ETA ~19:15 UTC
- Actual data: GAME 2641 + NAVWORLD 2248 + SWE-SYNTH 983 + LIVEWEB 18 = **5890 samples**
- ⚠️ **v2 excludes LGC-v2/PRINT** — coverage depends on base model retention

## Training Data (v2)

| Env | Count | Notes |
|-----|-------|-------|
| GAME | 2641 | 7 active games, 75.1% learnable, includes bot data |
| NAVWORLD | 2248 | SFT plateau confirmed, DPO for Phase 3 |
| SWE-SYNTH | 983 | seq=8192 unlocks 49% complete entries |
| LIVEWEB | 18 | Safety net |
| LGC-v2 | 0 | ⚠️ EXCLUDED — risk of coverage degradation |
| PRINT | 0 | ⚠️ EXCLUDED — risk of coverage degradation |
| **Total** | **5890** | |

## Competitor Landscape (LIVE — Block 7772891, 6-env)

| Rank | Miner | GAME | LGC-v2 | LIVEWEB | NAVWORLD | PRINT | SWE-SYNTH |
|------|-------|------|--------|---------|----------|-------|-----------|
| 1 | affshoot | 50.03 | 90.20 | 19.08 | 15.72 | 79.27 | 53.19 |
| 2 | vera6 | 50.59 | 90.40 | 19.11 | 25.12 | 82.90 | 27.00 |
| 3 | wisercat | 47.06 | 86.80 | 18.07 | 23.88 | 80.30 | 39.39 |
| 4 | AnastasiaFantasy | 40.84 | 81.60 | 16.53 | 24.84 | 81.25 | 40.00 |
| 5 | RLStepone | 49.37 | 87.55 | 16.31 | 21.88 | 80.90 | 39.00 |
| 6 | coffie3 | 41.56 | 82.43 | 16.38 | 21.69 | 74.07 | 46.00 |

## Priority Roadmap — 阶段迭代制

**规则**: 未达阶段目标 → 小版本迭代(v2a, v2b...)直到达标 → 才进入下一阶段

### Phase 2 (当前): 基线 + GAME修复 — 目标: 上榜 + 6-env GM ≥20
- **v2**: GAME 2641 + seq=8192, 5890 samples (4 envs trained, 6 envs scored)
- **GAME目标**: ≥25
- **NAVWORLD目标**: ≥5 (确认SFT天花板)
- **SWE-SYNTH目标**: ≥10
- **LIVEWEB目标**: ≥15
- **LGC-v2/PRINT**: must stay ≥60 (base model retention)
- **GM目标**: 6-env GM ≥20
- v2 eval **MUST include all 6 envs** (at least check LGC-v2/PRINT scores)
- 若LGC-v2/PRINT degraded → v2a adds back 1500+1500 maintenance data
- 若GM<20 → v2a: 诊断最弱环境，针对性修复 → 迭代直到GM≥20

### Phase 3: DPO突破NAVWORLD — 目标: 6-env GM ≥28 (Top 4)
- NAVWORLD DPO (241对) — 5.7→15+ (突破SFT天花板)
- GAME DPO (589对) — 推高强项
- 若GM<28 → v3a: 调整DPO参数/数据 → 迭代

### Phase 4: 冲击Top 2 — 目标: 6-env GM ≥32
- SWE-SYNTH数据增量 + seq=16384
- GAME Zero-tier用DPO/RL
- LIVEWEB上游压缩 (需用户授权)
- 若GM<32 → 迭代

### Phase 5: 冲击 #1 — 目标: 6-env GM ≥35
- 全环境精细优化
- 数据配比A/B测试
- RL/MCTS for hard GAME games

## Rules Reference

Experiment protocol, loop flow, hard constraints, and key commands are in `CLAUDE.md` (single source of truth).
