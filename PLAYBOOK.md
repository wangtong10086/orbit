# Affine Forge Playbook

## Goal

Affine Leaderboard (Bittensor Subnet 120) **#1**.

## Active Environments

**Training and optimization**: GAME, NAVWORLD, **SWE-Infinite**, LIVEWEB
**Excluded**: LGC-v2, PRINT (user directive)

## Scoring Mechanism

- **6 environments on leaderboard** — GAME, LGC-v2, LIVEWEB, NAVWORLD, PRINT, SWE-INFINITE
- **Geometric mean** within each subset — any zero kills that subset
- **Higher layers weight exponentially more** — L6 (all 6 envs) = 32x L1
- We cover 4/6 envs max. Missing LGC-v2 + PRINT caps at L4.

## Current State — v2.23 COMPLETE (A/B: no reasoning-parser wins)

| Env | v2.17a | v2.17b | **v2.23 ckpt-550** | Delta |
|-----|--------|--------|---------------------|-------|
| GAME | 27.50 | **29.72** | **29.70** | ≈best |
| NW | **42.34** | 35.48 | 34.88 | -7.46 |
| **LW** | 5.78 | 4.17 | **17.68 NEW BEST** | +206% |

**reasoning-parser A/B** (same model): with=11.26/18.86, without=29.70/34.88. **Parser confirmed harmful.**
**LW single-turn fix works WITHOUT parser** — LW 17.68 is from data quality, not inference config.
**NW regressed** due to LW data dilution (12054 LW entries vs 1159 in v2.17a).

**Best per env**: GAME 29.70 (v2.23), NW 42.84 (v2.21), **LW 17.68 (v2.23)**

## Key Issue: NW/LW data volume trade-off

LW single-turn data (12054) dilutes NW training signal. Need to balance LW volume to protect NW.

**v2.24 direction**: reduce LW to ~2000-3000, keep NW 2961+, NO reasoning-parser, use ckpt ~80%.

## LW New Issue: Premature Stopping

Single-turn format fixed nav loops but model now stops after 3-11 steps (not enough to visit all pages). 41% answers have null GT because agent stopped early. Need multi-site trajectory training data.

## Data Status

| Env | Count | Format |
|-----|-------|--------|
| GAME | 9088 | v8 eval-aligned |
| NW | 2961 | V6 think-per-tool_call (multi-turn) |
| LW | 12054 | v11 single-turn (template think fix) |
| SWE-I | ~770 | THOUGHT+bash |
| Total | ~24873 | |

## Competitor Landscape (Block 7819242)

| Rank | Miner | GAME | NW | LW | SWE-I |
|------|-------|------|-----|-----|-------|
| 1 | luis1027 | 50.49 | 23.68 | 18.88 | 8.08 |
| 2 | papyrus-puppy | 48.07 | 30.72 | 17.41 | 6.00 |
| **ours** | — | 28.21 | **42.84** | 12.95 | — |

## Key Findings (v2.18-v2.23)

1. **Reasoning-parser qwen3** — enables thinking, fixes LW, but breaks NW tool_calls
2. **LW single-turn fix** — Qwen3 template drops `<think>` in multi-turn. 2627→12054 single-turn
3. **NW not affected by template** — but still broken by reasoning-parser
4. **GAME SFT ceiling ~25-28** — spatial games 0%, need GRPO
5. **LW cache bottleneck** — 30-72 errors from stooq. valid_mean=23.04
6. **Final save corruption** — always merge from numbered checkpoint
7. **gin_rummy responds to MCTS** (+8%), liars_dice regresses (-20%)

## Priority — STRATEGIC ANALYSIS NEEDED

**Not rushing to next training.** Each role must deep-analyze their env data before v2.24.

## Rules Reference

See `CLAUDE.md` for full rules.
