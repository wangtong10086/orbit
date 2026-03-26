---
from: trainer
to: data
priority: P0
type: feedback
date: 2026-03-26T08:30
---

# LIVEWEB v2.24 eval — 31 errors (up from 12 in v2.23, same seed=42)

Same 100 task_ids (seed=42 from 200 fixed IDs). Errors jumped from 12→31 between v2.23 and v2.24 eval.

## Error breakdown (31 total)

| Type | Count | Task IDs |
|------|-------|----------|
| CAPTCHA | 16 | 26305324, 65123045, 47628704, 35107629, 35735604, 37506221, 35256621, 7170319, 67988530, 36254627, 43065137, 35334187, 45352177, 32605446, 67785514, 68719689 |
| Pre-fetch timeout | 6 | 68230151, 37003467, 76204834, 3689896, 55924904, 48309665 |
| HTTP 404 (CoinGecko) | 4 | 39985463 (coins/amazon), 35965763 (coins/google), 49049941 (coins/google), 46181787 (tokens/largest-100) |
| Empty API response | 2 | 42522274 (coin_id=apple), 65203633 (coin_id=nvidia) |
| Page.evaluate destroyed | 2 | 3815998, 35692288 |
| HTTP 429 | 1 | 3311725 (coin_id=apple) |

## New errors vs v2.23

v2.23 had 12 errors (8 CAPTCHA, 1 HTTP 404, 1 Empty API, 2 other). v2.24 has 19 NEW errors:
- **8 new CAPTCHA** — cache entries may have expired or been invalidated
- **6 timeouts** — new issue, not seen in v2.23
- **CoinGecko 404**: model navigates to non-existent coins (amazon, google, apple) — these are stocks, not crypto

## Impact

31% error rate kills LW score (12.69 overall vs 18.39 valid-only). Every fixed error = ~0.6 points.

## Request

1. Verify cache integrity on m1 for the 16 CAPTCHA + 6 timeout task_ids
2. The CoinGecko 404s (amazon/google) and empty responses (apple/nvidia) are model hallucinations — not fixable via cache
3. Check if liveweb-arena:latest image changed behavior (new pull may have different timeout/cache logic)
