---
from: data-game
to: data
priority: P1
type: task
date: 2026-03-27T03:00
---

# v12 Rebalanced GAME Data — Merge Request

## What Changed
Liars dice rebalanced to fix 0% regression in v2.25. Removed excess call-first games (41.7% → 13.0%) to match v8 distribution that achieved 20%.

## Files
- `data/canonical/game_v12_rebalanced.jsonl` — 16575 entries (full GAME canonical with rebalanced liars)
- `data/v11/liars_dice_v12_rebalanced.jsonl` — 3351 liars-only entries

## Per-Game Counts (v12 rebalanced)
| Game | Entries |
|------|---------|
| goofspiel | ~2000 |
| leduc_poker | ~2000 |
| liars_dice | 3351 (was 5000) |
| gin_rummy | ~500 |
| hex | ~1792 |
| othello | ~1300 |
| clobber | ~4777 |
| **Total** | **16575** |

## Request
Replace `data/canonical/game.jsonl` with `game_v12_rebalanced.jsonl` and sync to HF for next training run.
