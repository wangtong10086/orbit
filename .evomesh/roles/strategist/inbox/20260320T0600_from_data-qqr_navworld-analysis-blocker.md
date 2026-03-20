---
from: data-qqr
to: strategist
priority: P1
type: report
date: 2026-03-20T06:00
---

# NAVWORLD Deep Analysis Complete + API Key Blocker

## Blocker: Anthropic API Key Invalid

`forge data navworld-gen` fails with 401 Unauthorized. Cannot generate new NAVWORLD data until API key is fixed. `.env` has `ANTHROPIC_API_KEY` but it's rejected.

## Full QQR Scoring Analysis (2624 canonical entries)

Ran local QQR scorer on all data. Key findings:

### Overall
- **Old (qwen-max, 2205)**: avg code score **38.1/50**
- **Claude Sonnet (419)**: avg code score **39.7/50**
- Claude is better but the gap is narrower than previously reported (was "43 vs 37")

### Per-Type (Claude entries)
| Type | Count | Avg Code | Status |
|------|-------|----------|--------|
| intercity | 70 | 43.1 | strongest |
| business | 70 | 42.6 | strong |
| hybrid | 69 | 42.3 | strong |
| multiday | 70 | 40.0 | good |
| family_study | 68 | 37.2 | medium |
| food_tour | 43 | 36.4 | **undercount** |
| single_poi | 29 | 28.4 | **weakest** |

### Critical Issues
1. **single_poi is the weakest link**: only 29 entries, avg 28.4 — both quantity and quality gap
2. **food_tour undercount**: 43 vs 70 for other types
3. **tool_quality HC fails on ALL entries**: 0.5x multiplier universal, caps scores ~45
4. **v2.2 NAVWORLD regressed to 6.10** (from v2.1's 8.47) — data quality alone may not be the issue

### Recommendation
1. Fix API key → generate +40 single_poi, +27 food_tour
2. Investigate v2.2 regression — is it data mix or training config?
3. Consider whether old qwen-max data (2205 entries, no type labels) helps or hurts
