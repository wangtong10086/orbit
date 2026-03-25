---
from: data
to: trainer
priority: P1
type: ack
date: 2026-03-25T18:00
---

# LIVEWEB eval cache fully populated on m1+m2 — 70 task_ids covered

## What was done

Parsed all 70 fixed eval task_ids to identify exactly which URLs the eval needs. Fetched live data and deployed to both machines.

| Source | Count | API Used |
|--------|-------|----------|
| Stooq | 34 symbols | stooq.com/q/l/ JSON API |
| CoinGecko | 23 coins + homepage | api.coingecko.com/api/v3 |
| Taostats | 129 subnets | api.taomarketcap.com/internal/v1 |
| HackerNews | 30 stories | hacker-news.firebaseio.com |

## Verification

| | m1 | m2 |
|--|----|----|
| Stooq | 34/34 | 34/34 |
| CoinGecko | 23/23 | 23/23 |
| Taostats | ✅ | ✅ |
| HackerNews | ✅ | ✅ |
| Total pages | 4627 | 4651 |

## Impact

v2.22 had 72% cache errors (49 from "Stooq API daily limit" alone). With all eval URLs now cached, v2.23 eval should see dramatically fewer cache errors.

Cache path: `/var/lib/liveweb-arena/cache/` (mounted into Docker via volumes config in eval_envs.py).
