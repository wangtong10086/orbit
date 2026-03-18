# PRINT Environment

## Key Facts
- Predict program output evaluation
- Single-turn Q&A format
- Requires think block closure + actual answer output
- Supports think blocks
- Not in current focus

## Data
- DDB total: 17,689 samples, avg score 0.734 (second highest)
- High quality (>= 0.7, <= 16K): 2,899 entries
- Cleaner: verify think block closure + actual answer present

## Training Inclusion
- Excluded in v6-v8 (focused on weak environments)
- Re-included in v9+ (geometric mean requires no gaps)
- v9: 2,899 entries, 21.8% share
- v10: 2,899 entries, 21.8% share
- Re-inclusion confirmed safe: did not hurt GAME or other env scores

## Leaderboard
- Our score: ~80 points
- Top competitors: 73-86 points
- Slightly behind leader (-0.45 at one point)

## Current Best / Status
- 2,899 entries, stable in training mix
- Competitive but not leading
- DPO pairs: 800 (capped)

## Improvement Directions
- Mostly maintenance
- Could push higher with more data or DPO alignment
- Low priority compared to GAME/NAVWORLD/SWE-SYNTH
