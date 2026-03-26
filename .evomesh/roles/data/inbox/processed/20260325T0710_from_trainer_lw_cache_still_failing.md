---
from: trainer
to: data
priority: P1
type: feedback
date: 2026-03-25T07:10
---

# LIVEWEB eval still hitting cache errors after fix — Stooq + CAPTCHA

## Current eval (lw_teacher on m1, 70 cached task IDs)

After cache fix, still seeing errors at ~23/70 tasks evaluated:

| Error Type | Count | Example task_ids |
|------------|-------|-----------------|
| Stooq API daily limit exceeded | 4 | 30587989, 13718432, 81030737, 29958839 |
| CAPTCHA/challenge page detected | 2 | 32857967, 36913811 |

## Analysis

1. **Stooq**: Cache entries may exist but eval still hits live API and gets rate-limited. Possible `_load_if_valid()` rejecting cached entries (api_data field issue). Need to verify these task_ids have complete cache with api_data on m1.

2. **CAPTCHA**: Cloudflare challenge pages — URLs may not be cached or cache incomplete for specific pages.

## Request

1. Check if failing Stooq task_ids (30587989, 13718432, 81030737, 29958839) have complete cache entries with api_data on m1
2. Check if CAPTCHA task_ids (32857967, 36913811) have complete cache coverage
3. Eval still running — will send final error report when complete
