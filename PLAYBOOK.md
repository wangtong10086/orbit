# Affine Forge Playbook

## Goal

Affine Leaderboard (Bittensor Subnet 120) **#1**.

## Active Environments

**训练和优化**: GAME, NAVWORLD, **SWE-Infinite** (replacing SWE-SYNTH), LIVEWEB
**禁止训练**: LGC-v2, PRINT（用户明确指令）
**已废弃**: SWE-SYNTH（替换为 SWE-Infinite，data-swe 角色负责）

## Scoring Mechanism

- **Subset scoring**: all environment combinations evaluated
- **Geometric mean** within each subset — any zero kills that subset
- **Higher layers weight exponentially more** — L6 (all 6 envs) = 32x L1
- GAME scheduling weight 3.0 = sampled 3x more (data points), NOT scored higher
- **NAVWORLD弱则全盘皆输** — GM最大瓶颈

## Current State

- Ranking: Not deployed
- Model: Qwen3-32B QLoRA SFT
- Machine: 4xH200 (576GB VRAM, 2.8T disk) — ✅ **ONLINE**
- **v2.4a: BEST GM≈13.4** — GAME 26.03, **NAVWORLD 7.71**, LIVEWEB 11.90 (seq=8192)
- **v2.5: COMPLETE** — 24.28/6.51/11.82 (loss 0.288 异常, 全面不如 v2.4a)
- **v2.6: TRAINING (M2)** — seq=8192, lr=1e-4, 6191 samples
- **v2.7: APPROVED (M1)** — seq=8192, **lr=5e-5**, 6204 samples. 双机 lr A/B

## Training History

| Version | GAME | NAVWORLD | LIVEWEB | Loss | Key Change |
|---------|------|----------|---------|------|-----------|
| v2.1 | 25.74 | 8.47 | — | 0.156 | Baseline, seq=8192, 1-GPU |
| v2.2 | 26.04 | 6.10 | 6.83 | 0.224 | seq=16384, 4-GPU DDP |
| v2.3 | 22.69 | 1.52 | 8.62 | 0.172 | qwen-max 污染导致退步 |
| v2.4a | **26.03** | **7.71** | 11.90 | 0.231 | **seq=8192 GM最高** |
| v2.4b | 25.44 | 4.58 | **15.77** | ~0.17 | seq=16384 LIVEWEB最佳 |
| v2.5 | 24.28 | 6.51 | 11.82 | **0.288** | loss异常, 全面退步 |

## BLOCKERS

无。v2.5 已批准，M2 训练中。

## Competitor Landscape (Block 7784716)

| Rank | Miner | GAME | NAVWORLD | SWE | LIVEWEB |
|------|-------|------|----------|-----|---------|
| 1 | wisercat | 45.60 | 23.36 | 45.00 | 18.64 |
| 2 | vera6 | 48.85 | 21.94 | 31.00 | 18.10 |
| 3 | AnastasiaF | 47.74 | 17.87 | 37.37 | 23.21 |
| 4 | AnastasiaF-2 | 38.09 | 19.33 | 44.00 | 16.00 |
| 5 | RLStepone | 45.80 | 18.86 | 41.00 | 13.43 |
| 6 | coffie3 | 37.90 | 21.01 | 47.00 | 15.39 |

## Data Status (2026-03-20 16:00 UTC)

| Env | Canonical | v2.5 Training | Source |
|-----|-----------|---------------|--------|
| GAME | 3918 | 3918 | Bot + GPT-5.4蒸馏 (7游戏均衡) |
| NAVWORLD | **1157** | **1157** | GPT-5.4 + Claude (零qwen-max, 100%工具多样) |
| LIVEWEB | 400 | 400 | 历史 + GPT-5.4 |
| SWE-Infinite | **22轨迹** | 未纳入 | Go 21 + Ruby 1, 待v2.6纳入 |
| **总计** | — | **5475** | |

## Priority Roadmap

### Phase 2 (当前): SFT基线 — 目标: 上榜

- **v2.3** (training): GAME v4 + LIVEWEB format fix
- **v2.4** (next): NAVWORLD GPT-5.4 全面替换 qwen-max
- 目标: GAME ≥35, NAVWORLD ≥12, LIVEWEB ≥10

### Phase 3: GRPO突破 — 目标: Top 4

- GAME GRPO (verifiable reward)
- NAVWORLD RC-GRPO (multi-turn tool calling)
- SWE-Infinite RLVR (binary pass/fail)
- See: `knowledge/training.md`

### Phase 4: 冲击 #1 — 目标: GM ≥35

- 全环境精细优化
- 数据持续扩展

## Rules Reference

Experiment protocol, loop flow, hard constraints, and key commands are in `CLAUDE.md` (single source of truth).
