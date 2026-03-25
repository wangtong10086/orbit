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

## Current State

- **v2.23: TRAINING (M2)** — 606/657 (92%), ~15m. Unified think-before-action + reasoning-parser eval.
- **Best models**: v2.17a (NW 42.84 #1 globally), v2.20 (GAME 28.21)
- Machines: 2× 4xH200 (m1, m2)

## Training History (key versions only)

| Version | GAME | NW | LW | Data | Key Change |
|---------|------|-----|-----|------|-----------|
| v2.17a | 27.50 | **42.34** | 5.78 | 8401 | NW ALL-TIME BEST (no reasoning-parser) |
| v2.17b | **29.72** | 35.48 | 4.17 | 8775 | Best GAME (SWE-I included) |
| v2.20 | 28.21 | 37.77 | 5.78 | 13830 | GAME v6 MCTS-stats, no reasoning-parser |
| v2.21 | 24.92 | **42.84** | 4.83 | 13342 | v7 prompt alignment, no reasoning-parser |
| v2.22 | 24.92 | 21.37 | 6.46 | 15416 | reasoning-parser ON but old NW/LW data → NW crashed |
| **v2.23** | **?** | **?** | **?** | **24873** | LW single-turn fix + reasoning-parser |

## Key Findings

1. **lr=5e-5, epochs=1, seq=8192** — locked config
2. **Reasoning-parser qwen3 required** — enables Qwen3 thinking mode
3. **LW single-turn fix** — Qwen3 template drops `<think>` in multi-turn intermediate steps. LW converted 2627→12054 single-turn.
4. **NW NOT affected** — tool messages don't shift `last_query_index`
5. **Reasoning-parser + tool_call conflict** — model must think BEFORE tool_call. NW/LW data now has think-before-tool_call.
6. **GAME SFT ceiling ~28-30** — hex/othello/clobber = 0% across 5+ versions. GRPO needed.
7. **LW cache is main bottleneck** — 72/100 errors from stooq cache. valid_mean=23.04 when cache works.
8. **Final save corruption** — always merge from numbered checkpoint, not `final/`
9. **content=None = 0** across all data, **tool_call_id = 0 missing**

## Data Status (v2.23)

| Env | Count | Format | Key |
|-----|-------|--------|-----|
| GAME | 9088 | v8 eval-aligned prompt | Single-turn, `<think>` in assistant |
| NW | 2961 | V6 think-per-tool_call | Multi-turn (safe — tool msgs don't affect template) |
| LW | 12054 | v11 single-turn | **Fixed**: each step = independent sys+user+asst |
| SWE-I | ~770 | THOUGHT+bash | Go only |
| **Total** | **~24873** | | |

## Competitor Landscape (Block 7819242)

| Rank | Miner | GAME | NW | LW | SWE-I |
|------|-------|------|-----|-----|-------|
| 1 | luis1027 | 50.49 | 23.68 | 18.88 | 8.08 |
| 2 | papyrus-puppy | 48.07 | 30.72 | 17.41 | 6.00 |
| **ours** | — | 28.21 | **42.84** | 5.78 | — |

## Priority

1. **v2.23 eval** — verify LW single-turn + reasoning-parser fixes work together
2. **Stooq cache fix** — LW from 6→20+ (infra fix, directive sent)
3. **GAME new data** — waiting for user/data-game
4. **SWE-I eval** — need Docker config in eval_envs.py
5. **GRPO** — spatial games (Phase 3)

## Rules Reference

See `CLAUDE.md` for full rules.
