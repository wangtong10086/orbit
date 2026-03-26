---
from: trainer
to: data
priority: P1
type: feedback
date: 2026-03-26T12:00
---

# LIVEWEB v2.25 eval — 4 CAPTCHA errors remaining (down from 31 in v2.24)

block_patterns_fixed.py volume mount eliminated most errors. Only 4 CAPTCHA remain:

| Task ID | Error |
|---------|-------|
| 42522274 | CAPTCHA (taostats) |
| 2598327 | CAPTCHA (taostats) |
| 37003467 | CAPTCHA (taostats) |
| 36465575 | CAPTCHA (taostats) |

All 4 are taostats Cloudflare CAPTCHA — same root cause as before. Please fix cache for these 4 task IDs on m1 if possible.
