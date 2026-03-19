# NAVWORLD Claude Quality Scoring Results (N1)

**Date**: 2026-03-19
**Method**: Claude Haiku scored 200 random NAVWORLD entries on 5 eval-aligned dimensions
**Cost**: ~$0.19 (446K input + 65K output tokens)

## Results

| Dimension | Avg Score | /10 |
|-----------|-----------|-----|
| analysis_depth | 3.9 | Low — mostly data listing |
| factual_grounding | 3.5 | **WORST** — plans cite data not in tools |
| practicality | 3.9 | Missing transport details/time slots |
| logic | 3.6 | Route logic unclear |
| user_experience | 3.5 | Template feel, ignores constraints |
| **Total** | **7.5** | **/50** |

## Distribution
- 0-4: 133 entries (66.5%)
- 5-9: 19 entries (9.5%)
- 10-19: 30 entries (15%)
- 20-29: 11 entries (5.5%)
- 30-39: 7 entries (3.5%)
- 40-50: 0 entries (0%)

## #1 Issue: Factual Grounding (130/200 weakest)
Plans mention flight/train numbers, prices, POI names NOT from tool results.
This is catastrophic for eval: fabrication_penalty = up to -12.5 pts, transport_grounded gate = 0.3x.

## Common Problems
1. **Fabricated transport numbers**: plans cite CA1234, D9606 etc not in search results
2. **Wrong dates**: weather data from March used for April/May trips
3. **Invented POI details**: restaurant names, prices not from poi_search/around_search
4. **No trade-off analysis**: "recommended because comfortable" without WHY data

## Action: N2 Rewriting
Target bottom 40 entries (total < 2.8). Rewrite plans to:
- Only cite data verbatim from tool results
- Add genuine trade-off reasoning
- Fix date mismatches
- Ground every claim in a specific tool result
