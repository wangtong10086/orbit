# Affine Forge Playbook

## Goal

Affine Leaderboard (Bittensor Subnet 120) **#1**.

## Active Environments

**Training and optimization**: GAME, NAVWORLD, **SWE-Infinite**, LIVEWEB
**Excluded**: LGC-v2, PRINT (user directive)
**On leaderboard but excluded**: SWE-SYNTH (replaced by SWE-Infinite)

## Scoring Mechanism

- **7 environments on leaderboard** — GAME, LGC-v2, LIVEWEB, NAVWORLD, PRINT, SWE-INFINITE, SWE-SYNTH
- **Geometric mean** within each subset — any zero kills that subset
- **Higher layers weight exponentially more** — L7 (all 7 envs) = 64x L1
- GAME scheduling weight 3.0 = sampled 3x more (data points), NOT scored higher
- **Missing envs = catastrophic** — we cover 3/7 envs, competitors cover 7/7

## Current State

- Ranking: Not deployed
- Model: Qwen3-32B QLoRA SFT
- Machines: 2× 4xH200 (m1, m2) — ✅ **ONLINE**
- **v2.7: BEST GAME/LW** — GAME 28.90, NAVWORLD 12.63, LIVEWEB 13.76 (lr=5e-5)
- **v2.12: EVAL RUNNING** (m2) — v2.7 proportions + V5 NW + AMAP fixed. NW ~15.5 (55/100, **NEW BEST**), LW 13.12 (FINAL), GAME eval in progress.
- **AMAP key discovery**: v2.10/v2.11 NW scores were INVALID (API key missing on M2). Fixed for v2.12.

## Training History

| Version | GAME | NAVWORLD | LIVEWEB | Loss | Key Change |
|---------|------|----------|---------|------|-----------|
| v2.1 | 25.74 | 8.47† | — | 0.156 | Baseline, seq=8192 |
| v2.4a | 26.03 | 7.71† | 11.90 | 0.231 | seq=8192 GM best |
| v2.6 | 26.66 | 5.82† | 11.73 | 0.301 | lr=1e-4 control |
| **v2.7** | **28.90** | **12.63** | **13.76** | 0.348 | **lr=5e-5 — BEST GAME/LW** |
| v2.8 | 24.71 | 6.60 | 4.00 | 0.170 | epochs=2 FAILED |
| v2.9 | 26.48 | 8.36 | 6.42 | 0.266 | Less data hurts |
| v2.10 | 24.73 | 11.08⚠️ | 12.08 | — | ⚠️ NW invalid (AMAP missing) |
| v2.11 | 26.17 | 8.70⚠️ | 12.37 | 0.329 | ⚠️ NW invalid. SWE-I removed. |
| **v2.12** | **eval** | **~15.5** | **13.12** | 0.332 | **v2.7 proportions + AMAP fixed** |

†code-only NW (max 50). v2.7+ CHUTES LLM scoring (max 100). ⚠️ AMAP key missing.

## Key Findings

1. **lr=5e-5 > lr=1e-4** — v2.7 beats v2.6 on all envs
2. **seq=8192 > seq=16384** — for overall GM (NW tool-calling preserved)
3. **epochs=1 only** — epochs=2 overfits (v2.8)
4. **SWE-I is toxic** — removing 215 coding entries recovered GAME +8% (v2.11)
5. **GAME v11 MCTS data** — all 7 games now have MCTS bot data (60-80% win). Replaces old v10 minimax (only 3 games scored). Potential GAME breakthrough.
6. **AMAP key was NW bottleneck** — v2.10/v2.11 NW evals ran with 95% tool failures. v2.12 with fixed key shows NW ~15.5 (+22% over v2.7)
7. **Data proportions matter** — v2.7 had GAME 59%, NW 26%, LW 15%. Deviating hurts.
8. **Data volume matters** — removing data always hurts (v2.9)

## Data Status (2026-03-22 12:10 UTC)

| Env | Canonical | Status |
|-----|-----------|--------|
| GAME | **4462 (v11 MCTS)** | **Major update**: all 7 games with MCTS bot data (60-80% win). Old 5888 replaced. |
| NAVWORLD | 1626 (V5) | Format-corrected, eval-aligned, growing |
| LIVEWEB | 754 | Format fixes + multi-step 48% |
| SWE-Infinite | 131 | Docker-verified. Excluded from training. |

## Competitor Landscape (Block 7798081)

| Rank | Miner | GAME | NAVWORLD | LIVEWEB | SWE-I | LGC-v2 | PRINT |
|------|-------|------|----------|---------|-------|--------|-------|
| 1 | affshoot | 47.06 | 27.92 | 20.81 | 12.37 | 89.56 | 82.72 |
| 2 | AnastasiaF | 46.51 | 18.68 | 22.71 | 12.00 | 90.00 | 83.60 |
| 3 | wisercat | 46.54 | 27.93 | 18.89 | 8.00 | 89.07 | 82.29 |
| 4 | vera6 | 48.52 | 25.04 | 17.94 | 10.20 | 88.00 | 87.23 |
| 5 | RLStepone | 45.53 | 24.43 | 14.76 | 9.09 | 90.40 | 83.94 |

## Priority Roadmap

### Phase 2 (current): SFT optimization — target: deploy

- v2.12 EVAL RUNNING (m2) — GAME ~26 (62/100), NW 10.41 (99/100, below v2.7), LW 13.12 (FINAL)
- **v2.13 TRAINING (m1)** — GAME v11 MCTS 4462 + NW 1636 + LW 754 = 6852. 25/221 steps. ETA ~14:00 UTC.
- Target: GAME ≥35, NAVWORLD ≥15 (with AMAP), LIVEWEB ≥14

### Phase 3: GRPO + coverage — target: Top 6

- GAME GRPO (5 zero-score games)
- SWE-INFINITE scale-up (126→200+ trajectories)
- Re-evaluate LGC-v2/PRINT exclusion (strategic cost)

### Phase 4: Top 4 push — target: GM ≥35

- Full env optimization
- Method switching (DPO/GRPO per env)

## Rules Reference

Experiment protocol, loop flow, hard constraints, and key commands are in `CLAUDE.md` (single source of truth).
