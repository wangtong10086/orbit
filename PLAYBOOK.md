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
- **v2.8: EVAL** (m2) — epochs=2, lr=7e-5, final loss 0.17. GAME 24/100, NW 23/100, LW 72/100.
- **v2.9: TRAINING** (m1) — GAME 3-game filter (3101), lr=5e-5, 82% complete
- **v2.10: APPROVED** — NW V5 format-corrected (1348 entries). Launch on first free machine.

## Training History

| Version | GAME | NAVWORLD | LIVEWEB | Loss | Key Change |
|---------|------|----------|---------|------|-----------|
| v2.1 | 25.74 | 8.47† | — | 0.156 | Baseline, seq=8192 |
| v2.4a | 26.03 | 7.71† | 11.90 | 0.231 | seq=8192 GM best |
| v2.4b | 25.44 | 4.58† | **15.77** | ~0.17 | seq=16384 LW best |
| v2.6 | 26.66 | 5.82† | 11.73 | 0.301 | lr=1e-4 control |
| **v2.7** | **28.90** | **12.63** | 13.76 | 0.243 | **lr=5e-5 wins** |
| v2.8 | — | — | — | — | epochs=2, lr=7e-5 |

†code-only NAVWORLD (max 50). v2.7+ includes CHUTES LLM scoring (max 100).

## Key Findings

1. **lr=5e-5 > lr=1e-4** — v2.7 beats v2.6 on all envs
2. **seq=8192 > seq=16384** — for overall GM (NW tool-calling preserved)
3. **NAVWORLD V5 format fixes** — all prior data has wrong transport/prompt/schema format
4. **GAME SFT ceiling** — only 3/7 games score. 5 games need GRPO.
5. **CHUTES LLM scoring** — was missing pre-v2.7. True NW scores likely higher.

## BLOCKERS

- ~~NAVWORLD V5~~ — **DONE** (1348 entries merged). v2.10 approved.
- **SWE-INFINITE** — only 15 real trajectories. Too few for meaningful scores.

## Competitor Landscape (Block 7793424)

| Rank | Miner | GAME | NAVWORLD | LIVEWEB | SWE-I | LGC-v2 | PRINT |
|------|-------|------|----------|---------|-------|--------|-------|
| 1 | affshoot | 47.44 | 24.14 | 20.40 | 17.35 | 89.11 | 82.54 |
| 2 | wisercat | 44.71 | 24.46 | 19.71 | 6.00 | 90.40 | 84.66 |
| 6 | axon1 | 45.78 | 28.97 | 16.87 | 5.00 | 85.60 | 82.63 |

## Data Status (2026-03-21 11:30 UTC)

| Env | Canonical | Status |
|-----|-----------|--------|
| GAME | 2260 (v10) | Final — 3 SFT games, 5 games → GRPO |
| NAVWORLD | 1348 (V5) | ✅ Format-corrected, eval-aligned, HF synced |
| LIVEWEB | 464 | Stable. coingecko 317, stooq 68, hackernews 51 |
| SWE-Infinite | 15 | In progress. data-swe on m2 |

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
