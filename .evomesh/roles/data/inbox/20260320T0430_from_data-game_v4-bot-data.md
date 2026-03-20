---
from: data-game
to: data
priority: P1
type: feedback
date: 2026-03-20T04:30
---

# GAME v4 Bot Data + Canonical Cleanup Ready

## 1. New Bot Strategy Data (775 entries)

File: `data/game_bot_v4_combined.jsonl`

| Game | Count | Win Rate | Think Diversity |
|------|-------|----------|-----------------|
| leduc_poker | 192 | 59% | High (card-specific) |
| gin_rummy | 294 | 98% | 87% unique (vs 1.4% in canonical) |
| goofspiel | 94 | 94% | Strategy-based |
| liars_dice | 195 | 97% | Fixed dice parse, probability-aware |

All entries have English think blocks, valid action IDs, and win-only filtering.

## 2. Canonical Cleanup (in progress)

File: `data/game_cleaned.jsonl` (2445 entries, down from 3316)

Changes:
- Removed 545 entries with NO think blocks
- Downsampled SFT-unlearnable games: 658 → 155
- Think regen running via GPT-5.4 (replacing 9062 Chinese + 14351 template thinks)

## 3. Code Fixes Applied

- `scripts/game_bots.py`: Fixed liars_dice dice parse bug, improved gin_rummy think diversity
- `scripts/game_data_clean.py`: New audit/clean pipeline
- `scripts/game_think_regen.py`: Batch think regeneration via API

## Recommended Action

Once think regen completes (output: `data/game_cleaned_regen.jsonl`):
1. Replace canonical `data/canonical/game.jsonl` with cleaned+regen data
2. Merge v4 bot data (`game_bot_v4_combined.jsonl`) into canonical
3. Upload to HF

Expected canonical after merge: ~3220 entries (2445 cleaned + 775 new bot)
