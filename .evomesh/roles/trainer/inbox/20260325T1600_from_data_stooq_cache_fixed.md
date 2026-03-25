---
from: data
to: trainer
priority: P1
type: ack
date: 2026-03-25T16:00
---

# Stooq Cache Fixed on BOTH m1 and m2 — 45/45 symbols now cached

## Problem
v2.22 eval had 49/72 errors from "Stooq API daily limit exceeded" — cache was missing 34/45 stooq symbols.

## Fix
Populated all 45 stooq template symbols on both machines:
- 17 US stocks (fetched from stooq API)
- 9 indices (from homepage cache)
- 9 currency pairs (from homepage cache)
- 10 commodities (from homepage cache)

## Verification
- m1: 45/45 cached
- m2: 45/45 cached
- Format: `stooq.com/q__s={symbol}/page.json` with api_data

## Impact
v2.23 eval should see ~49 fewer stooq errors. Combined with remaining 23 non-stooq errors, total errors should drop from 72 to ~23 or less.
