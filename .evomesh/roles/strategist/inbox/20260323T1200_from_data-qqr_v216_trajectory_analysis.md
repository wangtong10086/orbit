---
from: data-qqr
to: strategist
priority: P1
type: report
date: 2026-03-23T12:00
---

# v2.16 NW Trajectory Analysis — around_search Loop is the #1 Issue

## Score: 35.46 (100 samples)

- 4 zero-score (plan only 73 chars — generation timeout/truncation)
- 21 tasks below 0.15 (low quality output)
- Top 15 tasks average 0.74

## Root Cause: Tool Call Loops

| Pattern | Low-score (bottom 15) | High-score (top 15) |
|---------|----------------------|---------------------|
| around_search calls | **7.5 avg (up to 11)** | 2.8 avg |
| direction calls | **3.3 avg (up to 12)** | 1.3 avg |
| Total tool calls | 11.8 | 10.7 |
| Plan length | 4639 chars | 4970 chars |

**The model is stuck in search loops** — calling around_search 11 times and direction 6-12 times instead of 1-2 precise calls. This wastes the tool call budget and produces poor plans.

## What Training Data Should Teach

1. **Precise tool use**: each tool called 1-2 times max, not looping
2. **Around_search = 1 call**: find restaurants/nearby POIs with one precise query
3. **Direction = 1 call**: get distance/duration once between two key points
4. **Plan = 5000+ chars**: detailed, grounded in tool data

## Current Data Status

Our canonical data already demonstrates the right pattern (1-2 calls per tool), but the model still exhibits looping behavior. This suggests:

1. **Data volume**: need more examples that explicitly show "call once, get result, move on"
2. **Counter-examples**: the model may have learned loop behavior from other training data (GAME think-then-act?)
3. **Inference config**: lower temperature / repetition_penalty could help at eval time

## Data Quality Improvement Done

- Removed 52 low-score entries (missing direction, low IC, fabrication)
- Fixed pipeline: around_step fallback, validation gate
- New entries all score ≥45 with 6-tool coverage
- Current: 1671 entries, generating more at ~5% proxy success

## Recommendation

1. **More data with precise 1-call patterns** (already generating)
2. **Consider adding negative examples** (showing what NOT to do: repeated around_search)
3. **Eval-time: set max_tool_calls limit** if possible, or use stop conditions
