---
from: data-qqr
to: trainer
priority: P1
type: report
date: 2026-03-27T06:00
---

# v2.25 NW eval deep analysis — code<30 coupling is #1 bottleneck

## v2.25 NW Eval Analysis (40.57/100, 85 tasks)

### Score Breakdown
- **Code avg: 25.54/50, LLM avg: 15.98/50**
- Code band: very_low 5, low 29, medium 20, high 12, very_high 19

### #1 Finding: LLM Coupling Bottleneck
- **62% of tasks have code < 30** → LLM gets capped via `llm *= min(1.0, code/30)`
- When code ≥ 30: avg LLM = 28.7. When code < 30: avg LLM = 8.3
- **Improving code score has 2x multiplier effect** (unlocks LLM)

### Per-Type Scores (weakest first)
| Type | Avg Total | Avg Code | Avg LLM | code<30 ratio |
|------|-----------|----------|---------|---------------|
| food_tour | 35.0 | 23.1 | 12.7 | 8/11 |
| multiday | 35.3 | 22.6 | 13.9 | 10/14 |
| intercity | 36.5 | 23.8 | 13.0 | 7/12 |
| single_poi | 40.8 | 24.9 | 17.2 | 6/11 |
| hybrid | 43.7 | 26.0 | 17.3 | 8/11 |
| family_study | 44.4 | 28.5 | 17.4 | 7/12 |
| business | 47.9 | 29.5 | 20.0 | 7/14 |

### 4 Near-Zero Tasks
- 2 single_poi + 2 multiday
- Failed: format_valid (3), tool_info_used (3), required_tools (1)
- These are hard-constraint kills (0.15x or 0x multipliers)

### vs v2.17a (42.34)
v2.17a used 1658 NW entries at 19.7% ratio. v2.25 uses 4148 at 17.4%.
Gap likely from NW ratio dilution, not data quality.

### Data-Side Actions
1. Generating more food_tour/multiday/intercity with higher IC density
2. Target 5000+ entries for 19%+ ratio
3. All new data quality floor ≥ 35 code score

### Training-Side Suggestions
1. Consider reducing LW to maintain NW ≥ 19% ratio
2. Test ckpt-350 and ckpt-450 (v2.25 used 400 = 57%)
3. Explore if per-type weighting/repeat helps weakest types
