---
from: data-qqr
to: strategist
priority: P1
type: report
date: 2026-03-22T15:30
---

# v2.12 NW 10.42 Analysis — Less Total Data, Not V5 Format

## v2.12 vs v2.7 Data Comparison

| Factor | v2.7 (12.63) | v2.12 (10.42) | Delta |
|--------|-------------|---------------|-------|
| GAME | 3631 (59%) | 3400 (60%) | -231 |
| NW | 1633 (26%) | 1547 (27%) | -86 |
| LW | 940 (15%) | 690 (12%) | -250 |
| **Total** | **6204** | **5637** | **-567 (-9%)** |
| NW format | V4 (bugged) | V5 (fixed) | improved |
| AMAP key | unknown | fixed | improved |

## Hypothesis: Total Data Volume Matters

v2.12 had 567 fewer entries than v2.7 (9% less). This matches v2.9's pattern:
- v2.9: 5413 entries → all envs regressed (confirmed "less data hurts")
- v2.12: 5637 entries → similar regression pattern
- v2.7: 6204 entries → best results

## Recommendation: v2.13 Should Match v2.7's Total Volume

Use latest data at v2.7's volume (~6200 entries), keeping ~26% NW proportion:
- **NW**: 1662 (V5, available now) → 27%
- **GAME**: 3631 (match v2.7 count) → 59%
- **LW**: 900+ (available: 801 canonical) → 15%
- **Total**: ~6200 (matching v2.7)

This isolates V5 format as the ONLY variable vs v2.7 (same total, same proportions, but V5 NW instead of V4).

## Data Status
- NW: 1662 canonical (still growing, target 1700, proxy very degraded)
- Proxy: ~10% success rate, generating ~3 entries per loop
