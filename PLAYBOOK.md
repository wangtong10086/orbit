# Affine Forge Playbook

## Goal

Affine Leaderboard (Bittensor Subnet 120) **#1**.

## Active Environments

**Training**: GAME, NAVWORLD, SWE-Infinite, LIVEWEB, MEMORYGYM
**Excluded**: LGC-v2, PRINT (user directive)

## Scoring Mechanism

- **6 environments on leaderboard** — GAME, LGC-v2, LIVEWEB, NAVWORLD, PRINT, SWE-INFINITE
- **Geometric mean** within each subset — any zero kills that subset
- **Higher layers weight exponentially more** — L6 (all 6 envs) = 32x L1
- We cover 4/6 envs max. Missing LGC-v2 + PRINT caps at L4.

## Current State

**v2.28: RESTARTING on m3** — Full FT Qwen3-32B (ms-swift + ZeRO-3), 8x H200, seq=32k. 87382 entries. m3 container rebuilt, Trainer re-setting up environment.

**Best per env (QLoRA era)**: GAME 29.70 (v2.23), NW 42.84 (v2.21), LW 27.76 (v2.25)

## v2.28 — Full Fine-Tuning (current experiment)

| Item | Value |
|------|-------|
| Method | **Full FT** (was QLoRA r=64) |
| Framework | **ms-swift 4.0 + DeepSpeed ZeRO-3** |
| Model | Qwen3-32B, 32.8B trainable (100%) |
| Hardware | 8x H200 143GB (m3) |
| Data | 87382 entries |
| seq_len | 32768 |
| Batch | per_device=1, grad_accum=4, effective=32 |
| LR | 2e-5 cosine, warmup 3% |
| save_steps | 100 |
| Estimated steps | ~2730 |

## Data Status (v2.28)

| Env | Count | % | Notes |
|-----|-------|---|-------|
| GAME | 38663 | 44.2% | No think chains, all 7 games |
| MemoryGym | 20000 | 22.9% | ChromaDB interaction (97% truncated at 32k) |
| LW | 17108 | 19.6% | v20+HN, goto+stop, no think |
| NW | 10006 | 11.5% | 7 types balanced, GPT-5.4 |
| SWE-I | 1605 | 1.8% | Go-dominant, THOUGHT+bash |
| **Total** | **87382** | | |

## Competitor Landscape (Block 7837772)

| Rank | Miner | GAME | NW | LW | SWE-I | Weight |
|------|-------|------|-----|-----|-------|--------|
| 1 | EdmondMillion | 46.25 | 33.50 | 18.86 | **14.00** | 0.508 |
| 2 | luis1027 | 46.82 | 22.80 | 17.61 | 8.24 | 0.254 |
| 3 | vera6 | 47.05 | 22.85 | 18.41 | 8.00 | 0.127 |
| **4** | **RLStepone/h15** | **46.61** | **35.32** | **28.42** | 4.04 | 0.063 |
| 10 | Sanguineey | 44.52 | **39.12** | 19.68 | 6.59 | 0.000 |
| **ours** | — | 29.70 | **42.84** | 27.76 | — | not submitted |

**LW #1 lost to RLStepone (28.42 vs 27.76). NW lead shrinking. GAME gap -17. Urgency: HIGH.**

## Confirmed Rules

1. **NO reasoning-parser** — A/B tested, hurts all envs
2. **Full FT > QLoRA** — 380x parameter capacity, matches competitors
3. **ms-swift > custom scripts** — correct loss masking, tool call handling, chat template
4. **seq=32k** — 80% of LW was truncated at 8k
5. **No think chains for GAME** — competitors use bare action IDs
6. **Never upload HF during training** — caused m3 crash (I/O + RAM conflict)
7. **Checkpoint = ~428GB** — save_steps=100 to reduce overhead
8. **epochs=1 only** — v2.8 proved 2 epochs overfits catastrophically

## Rules Reference

See `CLAUDE.md` for full rules.
