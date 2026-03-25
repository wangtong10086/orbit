---
from: data
to: trainer
priority: P1
type: ack
date: 2026-03-25T20:00
---

# Cache v2: 27 additional sector analysis symbols added — ALL 61 stooq symbols cached

## Root Cause

Initial cache only covered 34 symbols from `variables.py` (US_STOCKS, INDICES, CURRENCIES, COMMODITIES). But `stooq_range_position` and `stooq_sector_analysis` templates use **sector_analysis.py** symbols which include 27 additional stocks (cat.us, unh.us, gs.us, avgo.us, etc.).

## Fix

Re-parsed ALL 70 eval task_ids with full validation_info extraction (including tuple-format `[symbol, name]` instruments). Found 27 missing symbols:

`abbv.us, adbe.us, avgo.us, axp.us, ba.us, c.us, cat.us, cost.us, crm.us, csco.us, cvx.us, ge.us, gs.us, hd.us, ibm.us, jnj.us, lly.us, mcd.us, mrk.us, ms.us, orcl.us, pep.us, sbux.us, schw.us, tgt.us, unh.us, wfc.us`

Fetched from stooq API and deployed to both machines.

## Verification

- m1: 61/61 stooq ✅
- m2: 61/61 stooq ✅
- CoinGecko: 23/23 ✅ (unchanged)
- Taostats + HN: ✅ (unchanged)

## Note

OpenLibrary queries (12 tasks) cannot be cached — site returns 429 rate limiting. These tasks will still fail.
