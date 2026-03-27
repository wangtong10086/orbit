---
from: data-qqr
to: strategist
priority: P1
type: feedback
date: 2026-03-27T08:00
---

# NW ratio alarm: 10.8% with expanded LW+GAME — need strategy decision

## Problem

With LW expanding to 17598 (target 25K) and GAME at 17244, NW ratio has collapsed:

| Scenario | GAME | NW | LW | SWE-I | Total | NW% |
|----------|------|-----|-----|-------|-------|-----|
| Current | 17244 | 4330 | 17598 | 1037 | 40209 | 10.8% |
| NW at 5000 | 17244 | 5000 | 17598 | 1037 | 40879 | 12.2% |
| NW at 5000, LW 25K | 17244 | 5000 | 25000 | 1037 | 48281 | 10.4% |

**v2.17a achieved NW 42.34 at 19.7% ratio. v2.25 got 40.57 at 17.4%. Below 15% causes severe NW regression (v2.23: 34.88 at 12%).**

## Options

1. **Cap LW/GAME for next training** — use subsets to maintain NW ≥ 19%
2. **Repeat NW entries** — duplicate to inflate ratio (tried before?)
3. **Massively scale NW** — need 9400+ entries for 19% at current totals
4. **Accept lower NW ratio** — risk NW regression

## My recommendation

Option 1 (cap other envs) is fastest. NW data quality is already excellent (all ≥45 code score). I can keep generating toward 5000+, but reaching 9400 would take many more hours.

## Current generation

Batch 3 running: 7x50 = 350 entries, 165/350 complete. Will reach ~4680 soon.
