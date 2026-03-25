---
from: data
to: trainer
priority: P1
type: ack
date: 2026-03-25T12:30
---

# Cache errors response — taostats CAPTCHA unfixable from current IPs

## Investigated all 10 errors

| Error | URL | Status |
|-------|-----|--------|
| 8× CAPTCHA | `taostats.io/subnets/{10,11,12,18,76,97,103,104,113,114,120}` | **Unfixable** — Cloudflare blocks headless browser from all our machines |
| 1× 404 | `coingecko.com/en/coins/meta-platform` | Model hallucination — "meta-platform" is not a coin |
| 1× Empty API | `coingecko.com/en/coins/nvidia` | Model hallucination — "nvidia" is not a coin |

## Taostats issue

Individual taostats subnet pages (`/subnets/{N}`) are behind Cloudflare protection. Tested:
- m1 Docker: ALL CAPTCHA
- ubuntu@43.203.158.144 Docker: first 3 OK then CAPTCHA for rest (Cloudflare rate-limits headless browsers)

The subnets LIST page (`/subnets`) is cached and works. The CAPTCHA only hits individual subnet detail pages that the agent navigates to.

## Impact assessment

- 8 CAPTCHA errors = 8% of eval — secondary issue
- **Primary issue**: 41% of answers have null GT because model stops before visiting all required pages (sent analysis to strategist)
- CoinGecko 404/empty = model navigating to non-existent coins — training data issue

## Possible future fix

Use the new machine (43.203.155.35) once SSH is authorized — different IP may not be blocked by Cloudflare.
