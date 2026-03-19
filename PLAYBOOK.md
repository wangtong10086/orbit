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
- Machine: 4xH200 (576GB VRAM, 2.8T disk) — ✅ **ONLINE**
- **v2.1: EVAL COMPLETE** — GAME=25.74 ✅ NAVWORLD=8.47 ✅ (both targets passed)
- **v2.2: READY** — NAVWORLD quality + seq=16384 + all-GPU DDP. Pending approval.

## BLOCKERS

None. v2.1 eval complete. Decision needed: deploy v2.1 or proceed to v2.2.

## Training Data Status

### v2.1 (COMPLETE, awaiting eval)

| Env | Count | Notes |
|-----|-------|-------|
| GAME | 2916 | canonical |
| NAVWORLD | 2648 | includes 400 D8 entries that score 0 on QQR |
| SWE-SYNTH | 983 | canonical |
| LIVEWEB | 347 | DDB entries |
| **Total** | **6894** | |

### v2.2 (DESIGNED, pending approval)

| Env | Count | Changes vs v2.1 |
|-----|-------|-----------------|
| GAME | 3084 | +168 (goofspiel 150 + leduc 18) |
| NAVWORLD | ~2500 | QQR-filtered (-465 low-score) + Claude Sonnet (+111+) |
| SWE-SYNTH | 983 | unchanged |
| LIVEWEB | 386 | +39 Claude distill (taostats 21 + stooq 18) |
| **Total** | **~6953** | **quality >> v2.1, esp. NAVWORLD** |

**Key insight**: qwen-max NAVWORLD scores 0 on QQR code scorer. Claude Sonnet scores 40-46/100. v2.2 dramatically better quality.

## Competitor Landscape (LIVE — Block 7779610)

| Rank | Miner | GAME | NAVWORLD | SWE-SYNTH | LIVEWEB | LGC-v2 | PRINT |
|------|-------|------|----------|-----------|---------|--------|-------|
| 1 | wisercat | 47.26 | 23.79 | 43.00 | 19.09 | 88.00 | 81.22 |
| 2 | affshoot | 49.39 | 17.74 | 44.00 | 19.58 | 89.60 | 81.03 |
| 3 | vera6 | 50.81 | 21.27 | 29.00 | 19.27 | 89.60 | 82.47 |
| 4 | RLStepone | 47.19 | 18.78 | 40.00 | 14.87 | 88.80 | 84.02 |
| 5 | AnastasiaFantasy | 40.43 | 21.57 | 42.00 | 15.93 | 81.20 | 82.20 |
| 6 | EdmondMillion | 45.57 | 20.06 | 36.00 | 14.13 | 86.40 | 83.16 |

**wisercat #1** (Block 7779610). 4-env GM ≈ 31.3. NAVWORLD 23.79 is key advantage.

## Priority Roadmap — 阶段迭代制

**规则**: 未达阶段目标 → 小版本迭代(v2a, v2b...)直到达标 → 才进入下一阶段

### Phase 2 (当前): 4-env基线 — 目标: 上榜 + 4-env GM ≥20

- **v2** (4-env): CANCELLED
- **v2.1**: COMPLETE (loss 0.1893), eval BLOCKED (sglang)
- **v2.2**: DESIGNED — NAVWORLD quality overhaul (Claude Sonnet + QQR filter)
  - Primary variable: NAVWORLD data quality (Claude vs qwen-max)
  - Expected: NAVWORLD 12-20, GAME 28-38, 4-env GM ≥20
- **GAME target**: ≥25
- **NAVWORLD target**: ≥12 (Claude Sonnet data + QQR filtering)
- **SWE-SYNTH目标**: ≥10
- **LIVEWEB目标**: ≥15
- **GM目标**: 4-env GM ≥20
- 若未达标 → v2.3 迭代

### Phase 3: GRPO突破GAME+NAVWORLD — 目标: 4-env GM ≥28 (Top 4)
- GAME GRPO — verifiable reward (胜负明确)
- NAVWORLD: RC-GRPO with Claude reward model (spec research complete)
- DPO备选: 如GRPO infra搭建耗时，用DPO快速突破
- See: `knowledge/training.md` (Phase 3+ Methods section)

### Phase 4: 冲击 #1 — 目标: 4-env GM ≥35
- SWE-SYNTH: RLVR + 数据增量 + seq=16384
- GAME Zero-tier: GRPO/MCTS
- 全环境精细优化

## Rules Reference

Experiment protocol, loop flow, hard constraints, and key commands are in `CLAUDE.md` (single source of truth).
