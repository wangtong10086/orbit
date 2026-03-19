# Affine Forge Playbook

## Goal

Affine Leaderboard (Bittensor Subnet 120) **#1**.

## Active Environments (4个)

**训练和优化**: GAME, NAVWORLD, SWE-SYNTH, LIVEWEB
**禁止训练**: LGC-v2, PRINT（用户明确指令：禁止6环境，所有阶段只训练4环境）

## Scoring Mechanism

- **Subset scoring**: all environment combinations are evaluated
- **Geometric mean** within each subset — any zero kills that subset
- **Higher layers weight exponentially more** — L6 (all 6 envs) = 32x L1
- GAME scheduling weight 3.0 = sampled 3x more (more data points), NOT scored higher
- **NAVWORLD弱则全盘皆输** — GM最大瓶颈
- **LGC-v2/PRINT 不训练** — 用户明确指令，接受这些环境的零分影响

## Current State

- Ranking: Not deployed
- Model: Qwen3-32B QLoRA SFT
- Machine: 4xH200 (576GB VRAM, 2.8T disk) — ✅ **ONLINE**, GPU 0 at 100%
- **v2: TRAINING RUNNING** — re-launched 2026-03-19 ~03:04 UTC, step 3/243, ~92s/step, ETA ~09:00 UTC. VRAM 86.6GB/144GB.
- Data: GAME 2641 + NAVWORLD 2248 + SWE-SYNTH 983 + LIVEWEB 18 = 5890 (v2, 4-env only)

## BLOCKERS

1. ~~Machine unreachable~~ → RESOLVED
2. ~~v2 训练丢失~~ → Trainer 已在新机器重新启动，训练中 (step 3/243)
3. **v2 eval pending** — ETA ~09:00 UTC. 完成后 merge LoRA → deploy sglang → eval GAME+NAVWORLD 100s.

## Training Data Status

### v2 (4-env, running/complete)

| Env | Count | Notes |
|-----|-------|-------|
| GAME | 2641 | 7 active games, 75.1% learnable, includes bot data |
| NAVWORLD | 2248 | 5-template diversity issue identified |
| SWE-SYNTH | 983 | seq=8192 unlocks 49% complete entries |
| LIVEWEB | 18 | Safety net |
| **Total** | **5890** | |

### v3 (planned, 4-env)

| Env | Count | Status |
|-----|-------|--------|
| GAME | 2824 (+183 D7 HIGH gin_rummy) | Merge pending |
| NAVWORLD | 2648 (+400 D6 Phase 1 diversity) | Generation pending |
| SWE-SYNTH | 983 | Ready |
| LIVEWEB | 18 | Ready |
| **Total** | **~6473** | 4-env only |

## Competitor Landscape (LIVE — Block 7776423)

| Rank | Miner | GAME | NAVWORLD | SWE-SYNTH | LIVEWEB | LGC-v2 | PRINT |
|------|-------|------|----------|-----------|---------|--------|-------|
| 1 | affshoot | 49.44 | 16.28 | 43.00 | 19.16 | 89.11 | 79.80 |
| 2 | vera6 | 50.56 | 22.52 | 30.00 | 19.44 | 90.40 | 82.56 |
| 3 | RLStepone | 48.73 | 20.34 | 38.00 | 15.93 | 87.60 | 80.81 |
| 4 | AnastasiaFantasy | 40.78 | 22.16 | 37.00 | 17.16 | 83.20 | 80.83 |
| 5 | EdmondMillion | 45.55 | 20.69 | 38.00 | 14.57 | 86.80 | 81.73 |
| 6 | coffie3 | 40.26 | 20.72 | 42.00 | 16.86 | 83.61 | 74.19 |

**Volatile leaderboard** — wisercat dropped off (was #1 last block). affshoot #1 with GM ≈ 40.8.

## Priority Roadmap — 阶段迭代制

**规则**: 未达阶段目标 → 小版本迭代(v2a, v2b...)直到达标 → 才进入下一阶段

### Phase 2 (当前): 4-env基线 — 目标: 上榜 + 4-env GM ≥20

v2 训练中 (step 3/243, ETA ~09:00 UTC 2026-03-19)。

- **v2** (4-env): 训练中，5890 samples, seq=8192, ~92s/step
- **v3** (4-env, planned): + D7 gin_rummy + D6 NAVWORLD diversity
- **GAME目标**: ≥25
- **NAVWORLD目标**: ≥5 (confirm SFT ceiling)
- **SWE-SYNTH目标**: ≥10
- **LIVEWEB目标**: ≥15
- **GM目标**: 4-env GM ≥20
- 若未达标 → v2a/v3 迭代

### Phase 3: GRPO突破GAME+NAVWORLD — 目标: 4-env GM ≥28 (Top 4)
- GAME GRPO — verifiable reward (胜负明确)
- NAVWORLD: data diversity expansion FIRST (D6), THEN GRPO
- DPO备选: 如GRPO infra搭建耗时，用DPO快速突破
- 详见: `knowledge/training_best_practices.md`

### Phase 4: 冲击 #1 — 目标: 4-env GM ≥35
- SWE-SYNTH: RLVR + 数据增量 + seq=16384
- GAME Zero-tier: GRPO/MCTS
- 全环境精细优化

## Rules Reference

Experiment protocol, loop flow, hard constraints, and key commands are in `CLAUDE.md` (single source of truth).
