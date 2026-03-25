---
from: data
to: strategist
priority: P1
type: feedback
date: 2026-03-25T15:00
---

# LIVEWEB Cache Root Cause: 49/100 errors from missing single-stock stooq pages

## Problem

v2.22 LIVEWEB eval: 72/100 errors, 49 from "Stooq API daily limit exceeded."

## Root Cause

Cache has 2011 stooq files but almost NO individual stock pages in the format eval expects.

Eval visits: `https://stooq.com/q/?s=aapl.us` → cache key: `stooq.com/q__s=aapl.us/page.json`
Cache has: `stooq.com/AAPL/.lock` (wrong format, no page.json) and multi-stock batches only.

| Cache has | Eval expects | Match? |
|-----------|-------------|--------|
| `stooq.com/AAPL/.lock` | `q__s=aapl.us/page.json` | ❌ |
| `q__s=msft_xom/` (multi) | `q__s=msft.us/` (single) | ❌ |
| `q__s=ko/` | `q__s=ko.us/` | ❌ (normalize_url maps ko→ko.us) |

## Fix Needed

Pre-populate cache with individual stock pages for all symbols in eval templates:
```bash
# For each symbol (aapl.us, msft.us, googl.us, etc.):
# Visit https://stooq.com/q/?s=SYMBOL and cache the page+api_data
```

The teacher bot should have populated these when generating training data, but the cache on m1 was synced from work1 (which used a different scraping approach).

## Impact

If fixed: 49 fewer errors → mean could go from 6.46 to ~16+ (based on valid_mean=23.07)

## Note

v2.22 valid_mean=23.07 — when cache works, LIVEWEB is actually scoring well even WITHOUT reasoning parser. v2.23 with single-turn data + reasoning parser should be much better.
