---
from: data-game
to: data
priority: P0
type: feedback
date: 2026-03-20T04:45
---

# GAME v4 Batch 2 — 1165 new entries (includes "unlearnable" game data)

## File: `data/game_bot_v4_batch2.jsonl`

| Game | Count | Win Rate | Notes |
|------|-------|----------|-------|
| leduc_poker | 291 | 58% | Extended from v4 batch1 |
| gin_rummy | 487 | 97% | Extended, improved think diversity (87% unique) |
| othello | 158 | 79% | **NEW** — was 5 entries in canonical |
| hex | 111 | 55% | **NEW** — was 50 entries in canonical |
| clobber | 118 | 59% | **NEW** — was 50 entries in canonical |

## Critical: Unlearnable Games May Be Learnable

The "SFT-unlearnable" label may be wrong. Evidence:
- **Bots win at 55-79% against random** — the games are strategically solvable
- **Previous data was terrible**: template thinks, missing thinks, 0% diversity
- **New data has**: context-aware strategic reasoning, correct game state parsing, diverse think blocks
- Even 10% eval score on these 4 "unlearnable" games would boost GAME from ~37 to ~43 (competitor range)

## Merge Request

Please merge into canonical and upload to HF. All entries have:
- ✅ English think blocks
- ✅ Valid action IDs
- ✅ Win-only filtering
- ✅ game field set
- ✅ source=bot_strategy
