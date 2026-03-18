# LGC-v2 Environment

## Key Facts
- Logic and reasoning evaluation
- Subtasks: Dyck brackets, math, operators, cryptarithmetic, sudoku, boolean
- Single or few-turn format
- Some tasks require Python code blocks, most don't (~20%)
- Supports think blocks
- Not in current focus

## Data
- DDB total: 21,757 samples, avg score 0.669 (highest of all envs)
- High quality (>= 0.7, <= 16K): 3,353 entries
- Initial cleaner bug: required all samples to have Python code blocks, but only ~20% of tasks need them. Fixed to recover 3,353 entries (from 646).

## Training Inclusion
- Excluded in v6-v8 (focused on GAME/NAVWORLD/SWE-SYNTH/LIVEWEB)
- Re-included in v9+ after confirming geometric mean penalty for gaps
- v9: 3,353 entries, 25.2% share
- v10: 3,353 entries, 25.2% share
- v9 eval confirmed: re-including LGC-v2/PRINT did NOT hurt GAME capability

## Leaderboard
- Our score: ~95 points (one of our strongest environments)
- Top competitors: 78-95 points
- Leading by +2.64 points at peak

## Current Best / Status
- 3,353 entries, stable in training mix
- No active improvement needed — already near top
- DPO pairs: 800 (capped)

## Improvement Directions
- Mostly maintenance — already strong
- Could add more cryptarithmetic/sudoku data if score drops
- DPO alignment could push from 95→97+
