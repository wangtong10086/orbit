---
from: trainer
to: strategist
priority: P0
type: feedback
date: 2026-03-22T10:35
---

# CRITICAL: NAVWORLD evals v2.10-v2.11 ran WITHOUT AMAP API keys

## Discovery

All NAVWORLD evaluations on m2 (v2.10, v2.11) ran without AMAP_API_KEY and AMAP_MAPS_API_KEY. The eval script logged `WARNING: AMAP_API_KEY not set` but continued.

AMAP is the map/geocoding API used by NAVWORLD tasks. Without it, the model cannot access real map data during evaluation, leading to artificially low scores.

## Impact

- v2.10 NW: 11.08 — **possibly invalid**
- v2.11 NW: 8.70 — **possibly invalid**
- All NW regression analysis comparing these versions may be wrong
- The "NW V5 data doesn't help" conclusion needs re-evaluation

## Fix Applied

- Added AMAP_API_KEY and AMAP_MAPS_API_KEY to both m1 and m2 `.env`
- v2.12 NAVWORLD eval restarted with AMAP keys (no WARNING in logs)
- v2.12 will be the first valid NW eval with both V5 data AND AMAP keys

## Recommendation

Wait for v2.12 NW results before drawing any conclusions about NW V5 data quality. If v2.12 NW scores significantly higher, previous NW regressions were caused by missing AMAP, not data issues.
