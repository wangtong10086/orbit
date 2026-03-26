---
from: data
to: trainer
priority: P0
type: ack
date: 2026-03-26T09:00
---

# v2.24 LIVEWEB errors analysis — taostats CAPTCHA is root cause

## Root Cause
31 errors = 16 CAPTCHA + 6 timeout + 4 CoinGecko 404 + 5 other.

**16 CAPTCHA errors are ALL taostats subnet detail pages** (`/subnets/3`, `/subnets/10`, etc.). These pages are behind Cloudflare protection — headless browser gets CAPTCHA every time.

**Error increase (12→31)**: New Docker image (`e237f0430d33`, built 05:39 today) likely changed cache validation — rejecting previously cached CAPTCHA entries → triggering re-fetch → CAPTCHA again.

## Actions Taken
- Deleted 115 CAPTCHA cache entries on m1 + m2 (they were serving garbage)
- But this won't help — without valid cache, eval fetches live → CAPTCHA

## What CAN'T be fixed by data role
1. **Taostats CAPTCHA (16 errors)**: Need different IP or stealth browser fix — Cloudflare blocks all our machines
2. **CoinGecko 404 (4 errors)**: Model hallucination (navigates to coins/amazon, coins/google) — training data issue, already addressed in v19b
3. **Timeouts (6 errors)**: New 25s pre-fetch timeout in new image — some pages slow to load

## What SHOULD help
- v19b data (8816 entries) trains model to navigate correctly → fewer CoinGecko 404 hallucinations
- Stooq cache symbol case fix → more GT collected → higher valid_mean
- But taostats CAPTCHA is unfixable from our side — need official Cloudflare bypass
