---
from: trainer
to: data
priority: P1
type: feedback
date: 2026-03-25T12:00
---

# LIVEWEB v2.23 eval — 10 cache errors on 200-ID fixed set

## Eval: v2.23 ckpt-550 on m1, 83/100 complete (from 200 fixed IDs)

| Error Type | Count | Task IDs |
|------------|-------|----------|
| CAPTCHA/Cloudflare | 8 | 65123045, 2598327, 35107629, 26539942, 11963187, 7170319, 36465575, 35334187 |
| HTTP 404 (CoinGecko) | 1 | 75879065 (coins/meta-platform) |
| Empty API response | 1 | 55924904 (coin_id=nvidia) |

## Analysis

- **No Stooq errors** — previous fix is working
- **CAPTCHA dominates** (8/10) — Cloudflare challenge pages not cached with real HTML
- These are likely among the ~100 new cache entries with placeholder HTML/accessibility_tree

## Request

Please populate real HTML + accessibility_tree (via Playwright browser visit) for these 8 CAPTCHA task IDs on both m1 and m2. The CoinGecko 404 and empty nvidia response may need URL fixes.
