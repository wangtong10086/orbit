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
- Machine: 4xH200 (576GB VRAM, 2.8T disk) — ✅ **ONLINE**
- **v2.7: BEST** — GAME 28.90, NAVWORLD 12.63 (first CHUTES eval), LIVEWEB 13.76 (lr=5e-5)
- **v2.8: FAILED** — GAME 24.71, NW 6.60, LW 4.0. epochs=2 total regression.
- **v2.9: DONE** — GAME 26.48, NW 8.36, LW 6.42. All regressed vs v2.7. Less data hurts.
- **v2.10: FAILED** — GAME 24.73, NW 11.08, LW 12.08. All regressed ~12% vs v2.7. NW V5 no improvement.
- **v2.11: TRAINING** (m2) — Remove SWE-I. Actual data: GAME 5888 + NW 1491 + LW 642 = 8021. 10/287 steps, ETA ~12:30 UTC.

## Training History

| Version | GAME | NAVWORLD | LIVEWEB | Loss | Key Change |
|---------|------|----------|---------|------|-----------|
| v2.1 | 25.74 | 8.47† | — | 0.156 | Baseline, seq=8192 |
| v2.4a | 26.03 | 7.71† | 11.90 | 0.231 | seq=8192 GM best |
| v2.4b | 25.44 | 4.58† | **15.77** | ~0.17 | seq=16384 LW best |
| v2.6 | 26.66 | 5.82† | 11.73 | 0.301 | lr=1e-4 control |
| **v2.7** | **28.90** | **12.63** | **13.76** | 0.243 | **lr=5e-5 wins — BEST** |
| v2.8 | 24.71 | 6.60 | 4.0 | 0.17 | epochs=2 FAILED — all regressed |
| v2.9 | 26.48 | 8.36 | 6.42 | 0.266 | 3-game filter — less data hurts |
| v2.10 | 24.73 | 11.08 | 12.08 | — | NW V5 + SWE-I 215 — all regressed ~12% |

†code-only NAVWORLD (max 50). v2.7+ includes CHUTES LLM scoring (max 100).

## Key Findings

1. **lr=5e-5 > lr=1e-4** — v2.7 beats v2.6 on all envs
2. **seq=8192 > seq=16384** — for overall GM (NW tool-calling preserved)
3. **epochs=1 only** — v2.8 epochs=2 → LIVEWEB=4.0 regression (overfitting small datasets)
4. **NAVWORLD V5 format fixes** — 1348 entries merged, eval-aligned
5. **GAME SFT ceiling** — only 3/7 games score. 5 games need GRPO.
6. **CHUTES LLM scoring** — was missing pre-v2.7. True NW scores likely higher.
7. **NW V5 format fixes ≠ score improvement** — v2.10 NW 11.08 vs v2.7 12.63. Format wasn't the bottleneck.
8. **SWE-I may be toxic** — v2.10 added 215 SWE-I entries (new type), all envs regressed ~12%. Testing in v2.11.

## BLOCKERS

- ~~NAVWORLD V5~~ — **DONE** (1348 entries merged). v2.10 approved.
- **SWE-INFINITE** — 39 trajectories, excluded from training (suspected toxic in v2.10).
- **LIVEWEB data surge** — 642 entries (up from 528), data roles productive.

## Competitor Landscape (Block 7798081)

| Rank | Miner | GAME | NAVWORLD | LIVEWEB | SWE-I | LGC-v2 | PRINT |
|------|-------|------|----------|---------|-------|--------|-------|
| 1 | affshoot | 47.06 | 27.92 | 20.81 | 12.37 | 89.56 | 82.72 |
| 2 | AnastasiaF | 46.51 | 18.68 | 22.71 | 12.00 | 90.00 | 83.60 |
| 3 | wisercat | 46.54 | 27.93 | 18.89 | 8.00 | 89.07 | 82.29 |
| 4 | vera6 | 48.52 | 25.04 | 17.94 | 10.20 | 88.00 | 87.23 |
| 5 | RLStepone | 45.53 | 24.43 | 14.76 | 9.09 | 90.40 | 83.94 |

## Data Status (2026-03-22 02:20 UTC)

| Env | Canonical | Status |
|-----|-----------|--------|
| GAME | 5888 (full) / 2260 (v10 SFT-only) | data-game in Phase 1 bot optimization, 764 new entries generated (not merged) |
| NAVWORLD | 1471 (V5) | ✅ Format-corrected, eval-aligned, incrementally growing |
| LIVEWEB | 528 | Growing. HN r2 complete, taostats gen. +44 since v2.10 |
| SWE-Infinite | 39 | Docker-verified. Batch complete, 5% fix rate bottleneck. |

## Priority Roadmap

### Phase 2 (current): SFT optimization — target: deploy

- **v2.8** (training m2): epochs=2 + lr=7e-5 test
- **v2.9** (training m1): GAME v10 cleaned data (only scoring games)
- **v2.10** (next): NAVWORLD V5 format-corrected data (highest ROI, blocked on V5)
- Target: GAME ≥30, NAVWORLD ≥18, LIVEWEB ≥15

### Phase 3: GRPO + coverage — target: Top 6

- GAME GRPO (5 zero-score games)
- SWE-INFINITE scale-up (15→200+ trajectories)
- Re-evaluate LGC-v2/PRINT exclusion (strategic cost)

### Phase 4: Top 4 push — target: GM ≥35

- Full env optimization
- Method switching (DPO/GRPO per env)

## Rules Reference

Experiment protocol, loop flow, hard constraints, and key commands are in `CLAUDE.md` (single source of truth).
