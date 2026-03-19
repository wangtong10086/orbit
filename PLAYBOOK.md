# Affine Forge Playbook

## Goal

Affine Leaderboard (Bittensor Subnet 120) **#1**.

## Active Environments (6个)

**训练和优化重点**: GAME, NAVWORLD, SWE-SYNTH, LIVEWEB
**维持覆盖**: LGC-v2, PRINT (不投入优化，但必须训练以维持非零分数)

## Scoring Mechanism

- **Subset scoring**: all environment combinations are evaluated
- **Geometric mean** within each subset — any zero kills that subset
- **Higher layers weight exponentially more** — L6 (all 6 envs) = 32x L1
- GAME scheduling weight 3.0 = sampled 3x more (more data points), NOT scored higher
- **NAVWORLD弱则全盘皆输** — GM最大瓶颈
- **LGC-v2/PRINT=0 也会严重拖累** — 所有含LGC-v2或PRINT的子集(L2-L6)都受影响

## Current State

- Ranking: Not deployed
- Model: Qwen3-32B QLoRA SFT
- Machine: 4xH200 (576GB VRAM, 2.4T disk) — 🔴 **UNREACHABLE** (2026-03-19)
- **v2: TRAINING COMPLETE (unverified)** — launched 2026-03-18 ~13:15 UTC, ETA was ~19:15 UTC. Machine unreachable, cannot confirm completion or run eval.
- Data: GAME 2641 + NAVWORLD 2248 + SWE-SYNTH 983 + LIVEWEB 18 = 5890 (v2, 4-env only)

## 🔴 BLOCKERS

1. **Machine unreachable** — cannot verify v2 training, run eval, or deploy. User must check/restart GPU rental.
2. **v2 excluded LGC-v2/PRINT** — strategic error corrected for v3. Data already exists (1500 each).

## Training Data Status

### v2 (4-env, running/complete)

| Env | Count | Notes |
|-----|-------|-------|
| GAME | 2641 | 7 active games, 75.1% learnable, includes bot data |
| NAVWORLD | 2248 | 5-template diversity issue identified |
| SWE-SYNTH | 983 | seq=8192 unlocks 49% complete entries |
| LIVEWEB | 18 | Safety net |
| **Total** | **5890** | |

### v3 (planned, 6-env)

| Env | Count | Status |
|-----|-------|--------|
| GAME | 2824 (+183 D7 HIGH gin_rummy) | Merge pending |
| NAVWORLD | 2648 (+400 D6 Phase 1 diversity) | Generation pending |
| SWE-SYNTH | 983 | Ready |
| LIVEWEB | 18 | Ready |
| LGC-v2 | 1500 | Ready (already in canonical) |
| PRINT | 1500 | Ready (already in canonical) |
| **Total** | **~9473** | |

## Competitor Landscape (LIVE — Block 7776423)

| Rank | Miner | GAME | NAVWORLD | SWE-SYNTH | LIVEWEB | LGC-v2 | PRINT |
|------|-------|------|----------|-----------|---------|--------|-------|
| 1 | wisercat | 47.14 | 24.11 | 42.00 | 19.47 | 87.90 | 80.90 |
| 2 | affshoot | 49.44 | 16.28 | 43.00 | 19.17 | 89.11 | 79.80 |
| 3 | vera6 | 50.56 | 22.52 | 30.00 | 19.44 | 90.40 | 82.81 |
| 4 | RLStepone | 48.73 | 20.34 | 38.00 | 15.98 | 87.60 | 80.61 |
| 5 | AnastasiaFantasy | 40.92 | 22.16 | 36.36 | 17.05 | 83.20 | 81.05 |
| 6 | EdmondMillion | 45.55 | 20.69 | 38.00 | 14.55 | 86.80 | 81.73 |

**wisercat leads by balance** — no env below 19.47. 6-env GM ≈ 43.3.

## Priority Roadmap — 阶段迭代制

**规则**: 未达阶段目标 → 小版本迭代(v2a, v2b...)直到达标 → 才进入下一阶段

### Phase 2 (当前): 6-env基线 — 目标: 上榜 + 6-env非零

**BLOCKER**: Machine unreachable. Waiting for user to resolve.

- **v2** (4-env): training should be complete but cannot verify
- **v3** (6-env, planned): adds LGC-v2/PRINT + D7 gin_rummy + D6 NAVWORLD diversity
- **GAME目标**: ≥25
- **NAVWORLD目标**: ≥5 (confirm SFT ceiling)
- **SWE-SYNTH目标**: ≥10
- **LIVEWEB目标**: ≥15
- **LGC-v2目标**: ≥70 (baseline with 1500 subsampled entries)
- **PRINT目标**: ≥60 (baseline with 1500 subsampled entries)
- 若未达标 → v3a/v3b 迭代

### Phase 3: GRPO突破GAME+NAVWORLD — 目标: 6-env GM ≥35 (Top 3)
- GAME GRPO — verifiable reward (胜负明确)
- NAVWORLD: data diversity expansion FIRST (D6), THEN GRPO
- DPO备选: 如GRPO infra搭建耗时，用DPO快速突破
- 详见: `knowledge/training_best_practices.md`

### Phase 4: 冲击 #1 — 目标: 6-env GM ≥43
- SWE-SYNTH: RLVR + 数据增量 + seq=16384
- GAME Zero-tier: GRPO/MCTS
- 全环境精细优化

## Rules Reference

Experiment protocol, loop flow, hard constraints, and key commands are in `CLAUDE.md` (single source of truth).
