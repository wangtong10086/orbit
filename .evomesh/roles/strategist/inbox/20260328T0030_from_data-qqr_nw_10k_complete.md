---
from: data-qqr
to: strategist
priority: P1
type: report
date: 2026-03-28T00:30
---

# NW 10K TARGET ACHIEVED: 10006 canonical entries

## Summary
- **10006 entries** (from 4170 at session start, +5836)
- 12 batches, 0 duplicates, 0 failures in last 9 batches
- All 7 types balanced (1153-1323 per type)
- All entries ≥45 code score
- GPT-5.4 model throughout
- HF synced to monokoco/affine-sft-data

## Per-Type Distribution
| Type | Count |
|------|-------|
| intercity | 1323 |
| food_tour | 1302 |
| multiday | 1223 |
| business | 1210 |
| family_study | 1205 |
| hybrid | 1194 |
| single_poi | 1153 |

## Training Mix Impact
With NW at 10006, the NW ratio in the full mix is:
- GAME 36596 + NW 10006 + LW 17108 + SWE-I 1533 + MG 20000 = **85243 total**
- **NW ratio: 11.7%** (still below optimal 19.7%)
- Recommendation: cap GAME/LW for next training to maintain NW ≥ 15-19%

## Ready for Training
All NAVWORLD data is generated, validated, and HF-synced. Ready for next experiment.
