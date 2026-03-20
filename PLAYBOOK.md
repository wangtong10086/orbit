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
- **v2.3: EVAL** — NAVWORLD 1.51 ⚠️, LIVEWEB 7.50, GAME running (44/100)
- **v2.4: APPROVED** — 移除qwen-max NAVWORLD + SWE-SYNTH, seq=8192, 立即启动

## Training History

| Version | GAME | NAVWORLD | LIVEWEB | Loss | Key Change |
|---------|------|----------|---------|------|-----------|
| v2.1 | 25.74 | 8.47 | — | 0.156 | Baseline, seq=8192, 1-GPU |
| v2.2 | 26.04 | 6.10 | 6.83 | 0.224 | seq=16384, 4-GPU DDP |
| v2.3 | ~26* | **1.51** | 7.50 | ~0.18 | NAVWORLD严重退步 (*GAME running) |
| v2.4 | — | — | — | — | 清理数据+seq=8192, 总4947条 |

## BLOCKERS

无。v2.4 数据就绪，等 v2.3 GAME eval 完成即启动。

## Competitor Landscape (Block 7784716)

| Rank | Miner | GAME | NAVWORLD | SWE | LIVEWEB |
|------|-------|------|----------|-----|---------|
| 1 | wisercat | 45.60 | 23.36 | 45.00 | 18.64 |
| 2 | vera6 | 48.85 | 21.94 | 31.00 | 18.10 |
| 3 | AnastasiaF | 47.74 | 17.87 | 37.37 | 23.21 |
| 4 | AnastasiaF-2 | 38.09 | 19.33 | 44.00 | 16.00 |
| 5 | RLStepone | 45.80 | 18.86 | 41.00 | 13.43 |
| 6 | coffie3 | 37.90 | 21.01 | 47.00 | 15.39 |

## Data Status (2026-03-20 11:15 UTC)

| Env | Canonical | v2.4 Training | Source |
|-----|-----------|---------------|--------|
| GAME | 3631 | 3631 | Bot策略, GPT-5.4蒸馏进行中 (~1190) |
| NAVWORLD | **919** | **919** | **清理后**: GPT-5.4 500 + Claude 341 + qwen3-max标记 78 |
| LIVEWEB | 397 | 397 | 历史341 + GPT-5.4 56 |
| SWE-SYNTH | 0 | **0** | 已废弃移除 |
| SWE-Infinite | 9轨迹 | 未纳入 | data-swe 收集中 (9/345) |
| **总计** | — | **4947** | 零垃圾数据 |

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
