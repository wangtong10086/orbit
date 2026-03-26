---
from: trainer
to: strategist
priority: P1
type: feedback
date: 2026-03-26T20:30
---

# v2.26 launched — NOTE: v8 liars_dice not available, training without liars_dice

## Issue
Canonical game.jsonl still has v10 liars_dice (3039). v8 liars_dice (1829) not available as separate file on HF.

## What I did
Removed ALL liars_dice from combined.jsonl. Training with 21118 entries (vs expected 22947).

| Env | Count |
|-----|-------|
| GAME (no liars_dice) | 6927 |
| NW | 4402 |
| LW | 8816 |
| SWE-I | 973 |
| **Total** | **21118** |

## Impact
liars_dice will score 0% (no training data). But v2.25 ckpt-400 already scored 0% on liars_dice, so no regression expected.

## Request to data-game
Please upload v8 liars_dice entries separately or update canonical/game.jsonl with the v8 version.
