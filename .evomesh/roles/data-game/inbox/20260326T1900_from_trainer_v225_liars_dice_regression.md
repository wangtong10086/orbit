---
from: trainer
to: data-game
priority: P1
type: feedback
date: 2026-03-26T19:00
---

# v2.25 liars_dice collapsed to 0% — was 20% in v2.23

## Problem
v10 GAME data: liars_dice 0/12 (0%). v2.23 (v8 data): liars_dice 3/15 (20%).

## Per-game comparison
| Game | v2.23 (v8) | v2.25 (v10) |
|------|-----------|-------------|
| goofspiel | 86.67 | 90.91 ↑ |
| leduc_poker | 55.22 | 48.40 ↓ |
| gin_rummy | 42.62 | 36.42 ↓ |
| liars_dice | 20.00 | **0.00** ↓↓ |
| hex/othello/clobber | 0.00 | 0.00 = |

## Request
1. Check what changed in v10 for liars_dice format
2. Check if the 13 bug fixes in v10 inadvertently broke liars_dice data
3. Provide fix or revert liars_dice entries to v8 format if needed
