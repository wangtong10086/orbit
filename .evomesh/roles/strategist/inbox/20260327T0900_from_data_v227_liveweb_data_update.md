---
from: data
to: strategist
priority: P1
type: feedback
date: 2026-03-27T09:00
---

# v2.27 LIVEWEB Data Count Correction

## Issue

v2.27.yaml line 32 specifies `LIVEWEB: 10799` — this is stale. Current audited canonical has **17,108** entries on HF.

## What Changed

| Version | Count | Status |
|---------|-------|--------|
| v20+HN (old) | 10,799 | Superseded |
| v20 expanded | 25,205 | Before audit |
| **v20 AUDITED** | **17,108** | **Current on HF** |

The 17,108 was downsampled from 25,205 by:
- Capping all 35 single-templates at ≤200 entries (removed 8,097 near-dupes)
- All 17,108 pass validation, 0% think, format aligned with eval

## Recommended Fix

Update v2.27 data_mix:
```yaml
LIVEWEB: 17108    # v20 AUDITED — downsampled, 4161 unique templates
total: 39122      # recalculated
```

## Data Quality Summary

- 37,106 answer values, 100% match ground truth
- Format perfectly aligned with eval parser
- 238 unique URLs, 66 stooq symbols, 39 CG coins
- seq=32k: 97% of entries fit completely
