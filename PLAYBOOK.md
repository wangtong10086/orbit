# Affine Forge Playbook

## Goal

Affine Leaderboard (Bittensor Subnet 120) **#1**.

## Active Environments

**Training and optimization**: GAME, NAVWORLD, **SWE-Infinite**, LIVEWEB
**Excluded**: LGC-v2, PRINT (user directive)
**Removed from leaderboard**: SWE-SYNTH (as of Block 7812719)

## Scoring Mechanism

- **6 environments on leaderboard** — GAME, LGC-v2, LIVEWEB, NAVWORLD, PRINT, SWE-INFINITE
- **Geometric mean** within each subset — any zero kills that subset
- **Higher layers weight exponentially more** — L6 (all 6 envs) = 32x L1
- GAME scheduling weight 3.0 = sampled 3x more (data points), NOT scored higher
- **Missing envs = catastrophic** — we cover 3-4/6 envs, competitors cover 6/6

## Current State

- Ranking: Not deployed
- Model: Qwen3-32B QLoRA SFT
- Machines: 2× 4xH200 (m1, m2) — m1 TRAINING, m2 idle
- **v2.18: CORRUPTED** — model outputs garbage (`!!!!`). Packing same as v2.13b-v2.17a (all worked), likely random event.
- **v2.19: ROOT CAUSE FOUND** — all checkpoints (50/300/350) ✅, only final save ❌. Corruption at save_pretrained, not training.
- **v2.19 ckpt-300 EVAL**: NW 19.45 (down from 42.34). Root cause: 49% tasks lost `<think>` → zero score. LW/SWE-I data dilutes think behavior.
- **v2.20: GAME 28.21, NW 37.77, LW ~89/100** — gin_rummy +8% but liars_dice -20%. NW down from 42.34. **ROOT CAUSE: training/eval system prompt mismatch → 0% think rate.** GAME v7 fix ready.
- **v2.21: TRAINING** (378/528 steps, 72%) — GAME v7 8259 (think alignment fix) + NW 1768 + LW 2627 + SWE-I 688 = 13342. ETA ~1h09m.
- **v2.17a: BEST** — GAME 27.50, **NW 42.34** (#1 globally), LW 5.78
- **v2.17b: A/B with SWE-I** — GAME 29.72 (best GAME), NW 35.48, LW 4.17

## Training History

| Version | GAME | NAVWORLD | LIVEWEB | Data | Key Change |
|---------|------|----------|---------|------|-----------|
| v2.7 | 28.90 | 12.63 | 13.76 | 6204 | lr=5e-5 baseline |
| v2.13b | 28.12 | 25.13 | 11.03 | 6852 | content=None fixed, NW +99% |
| v2.14 | 25.71 | 6.27 | 13.97 | 5887 | LW best but NW collapsed |
| v2.16 | 26.75 | 35.46 | 6.49 | 9266 | v12 think-then-act, NW +41% |
| **v2.17a** | **27.50** | **42.34** | 5.78 | 8401 | **NW ALL-TIME BEST** (no SWE-I) |
| v2.17b | **29.72** | 35.48 | 4.17 | 8775 | SWE-I helps GAME +8%, hurts NW -16% |
| v2.18 | **training** | — | — | **11272** | User-enhanced data + SWE-I |

## Key Findings

1. **lr=5e-5 > lr=1e-4** — v2.7 vs v2.6
2. **seq=8192 > seq=16384** — for overall GM
3. **epochs=1 only** — epochs=2 overfits (v2.8)
4. **Think-then-act = biggest win** — v12 system prompt fix: NW 25→42 via cross-training
5. **SWE-I trade-off** — GAME +8%, NW -16%, LW -48%. Include per user directive.
6. **Data volume always helps** — more data never hurts (v2.9 proved)
7. **GAME SFT ceiling ~27-30** — hex/othello/clobber near 0%. GRPO needed.
8. **LW nav loops** — think-then-act causes URL repetition loops in LIVEWEB
9. **content=None kills model** — validate before every training
10. **AMAP keys mandatory** — v2.10/v2.11 NW scores invalid without them
11. **Think dilution kills NW** — LW/SWE-I data without `<think>` blocks dilutes think behavior. 49% NW tasks lost think in v2.19 → NW 42→19. ALL data needs think blocks.
12. **Final save corruption** — v2.18/v2.19 final checkpoints corrupted but intermediate checkpoints work. Always merge from numbered checkpoint.

## Data Status (v2.18 training data)

| Env | Count | Notes |
|-----|-------|-------|
| GAME | 7096 | User-enhanced, ALL canonical |
| NAVWORLD | 1692 | V5 format-corrected |
| LIVEWEB | 1953 | User-enhanced |
| SWE-Infinite | 531 | ALL canonical |
| **Total** | **11272** | Largest dataset ever |

## Competitor Landscape (Block 7812719) — SWE-SYNTH REMOVED

| Rank | Miner | GAME | LGC-v2 | LIVEWEB | NAVWORLD | PRINT | SWE-I |
|------|-------|------|--------|---------|----------|-------|-------|
| 1 | wisercat | 47.56 | 92.37 | 15.68 | 30.58 | 79.79 | 6.32 |
| 2 | papyrus-puppy | 44.11 | 93.98 | 17.86 | 35.46 | 78.00 | 4.30 |
| 3 | vera6 | 47.54 | 91.97 | 16.85 | 24.91 | 80.00 | 4.40 |
| 4 | AnastasiaF | 40.56 | 82.73 | 19.01 | 25.92 | 77.89 | 7.37 |
| 5 | emglab-ai | 42.99 | 89.56 | 17.15 | 35.53 | 77.32 | 5.32 |
| 6 | luis1027 | 48.08 | 96.71 | 18.49 | 27.77 | 82.35 | 5.56 |
| **ours** | — | **29.72** | — | **13.97** | **42.34** | — | — |

**Key**: Our NW 42.34 is #1 globally (+19% over best competitor 35.53).

## Priority Roadmap

### Phase 2 (current): SFT optimization + deploy

- **v2.18 TRAINING** — user-enhanced data, largest dataset (11272). ETA ~3h.
- After v2.18: full 7-step process → formal report → root cause analysis
- Target: GAME ≥35, NW ≥40 (protect lead), LW ≥15, SWE-I >0

### Phase 3: GRPO + coverage — target: Top 6

- GAME GRPO for spatial games (hex/othello/clobber at 0%)
- SWE-INFINITE eval (531 entries, never evaluated — could be free points)
- LW adversarial recovery data (fix nav loops)
- Re-evaluate LGC-v2/PRINT exclusion (strategic cost with 6-env leaderboard)

### Phase 4: Top 4 push — target: GM ≥35

- Full env optimization
- Method switching (DPO/GRPO per env)

## Rules Reference

Experiment protocol, loop flow, hard constraints, and key commands are in `CLAUDE.md` (single source of truth).
