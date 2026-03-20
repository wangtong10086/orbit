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
- **v2.3: TRAINING** — loss 0.189 at step 150/194, ETA ~09:20 UTC
- **v2.4: APPROVED** — 移除SWE-SYNTH + NAVWORLD +225 GPT-5.4, 等v2.3 eval完立即启动

## Training History

| Version | GAME | NAVWORLD | LIVEWEB | SWE | Loss | Key Change |
|---------|------|----------|---------|-----|------|-----------|
| v2.1 | 25.74 | 8.47 | — | — | 0.156 | Baseline, 1-GPU seq=8192 |
| v2.2 | 26.04 | 6.10 ⚠️ | 6.83 | FAIL | 0.224 | 4-GPU DDP, seq=16384 |
| v2.3 | ? | ? | ? | skip | ~0.18* | GAME v4 all 7 games + LIVEWEB format fix |

## BLOCKERS

- **v2.4 data**: NAVWORLD GPT-5.4 generation in progress (data-qqr: 101+ entries, target ~1200)
- **SWE-Infinite**: data-swe building trajectory pipeline (345 R2 tasks verified)

## Competitor Landscape (Block 7784716)

| Rank | Miner | GAME | NAVWORLD | SWE | LIVEWEB |
|------|-------|------|----------|-----|---------|
| 1 | wisercat | 45.60 | 23.36 | 45.00 | 18.64 |
| 2 | vera6 | 48.85 | 21.94 | 31.00 | 18.10 |
| 3 | AnastasiaF | 47.74 | 17.87 | 37.37 | 23.21 |
| 4 | AnastasiaF-2 | 38.09 | 19.33 | 44.00 | 16.00 |
| 5 | RLStepone | 45.80 | 18.86 | 41.00 | 13.43 |
| 6 | coffie3 | 37.90 | 21.01 | 47.00 | 15.39 |

## Data Status (2026-03-20)

| Env | Canonical | v2.3 Training | v2.4 Planned | Source |
|-----|-----------|---------------|-------------|--------|
| GAME | 4657 | 3631 | ~4657 | Bot strategies + GPT-5.4 distill |
| NAVWORLD | 2725+ | 2624 | ~1600 (GPT-5.4 only) | Replacing qwen-max with GPT-5.4 |
| LIVEWEB | 365 | 388 | ~400+ | GPT-5.4 distill, no compression needed |
| SWE-Infinite | 0 | 983 (old) | TBD | data-swe pipeline building |

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
