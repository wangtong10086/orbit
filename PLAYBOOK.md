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

## Current State — v2.23 COMPLETE

| Env | v2.17a (no parser) | v2.20 (no parser) | v2.21 (no parser) | v2.23 (reasoning-parser) |
|-----|-------------------|-------------------|-------------------|--------------------------|
| GAME | 27.50 | **28.21** | 24.92 | 25.79 |
| NW | **42.34** | 37.77 | **42.84** | 19.45 ↓↓ |
| LW | 5.78 | 5.78 | 4.83 | **12.95** ↑↑ |

**v2.23 finding**: reasoning-parser fixes LW (+124%) but kills NW (-54%). GAME/NW trade-off persists.

**Best per env**: GAME 28.21 (v2.20), NW 42.84 (v2.21), LW 12.95 (v2.23)

## Key Issue: Cannot optimize all envs simultaneously

| Config | GAME | NW | LW | Problem |
|--------|------|-----|-----|---------|
| No reasoning-parser | ~28 | ~42 | ~6 | LW can't think → low |
| With reasoning-parser | ~25 | ~19 | ~13 | NW tool_calls broken |

**Root cause**: reasoning-parser captures NW tool_calls as reasoning content despite data fix. NW data is multi-turn (tool msgs) — reasoning parser still interferes.

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
