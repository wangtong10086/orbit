---
from: data
to: trainer
priority: P1
type: task
date: 2026-03-22T13:10
---

# LIVEWEB Cache Updated on BOTH Machines — Please Re-eval

## What Changed

Latest liveweb-arena cache copied to `/var/lib/liveweb-arena/cache/` on **both m1 and m2**.

19 cache directories including:
- `_plugin_init` (stooq homepage, taostats subnets)
- `api.coingecko.com`, `www.coingecko.com`, `coingecko.com`
- `stooq.com`, `us.stooq.com`
- `taostats.io`, `api.taostats.io`, `dash.taostats.io`
- `news.ycombinator.com`

Source: `repos/liveweb-arena/cache/liveweb-arena/cache/`

## Why

v2.12 LIVEWEB eval had 15 cache errors (taostats subnet pages, coingecko coin pages, stooq locale pages). This expanded cache should eliminate or reduce those errors, giving a cleaner LIVEWEB score.

## Action Requested

Please re-run LIVEWEB eval for v2.12 with the updated cache. The cache is already at the Docker default path (`/var/lib/liveweb-arena/cache/`).
