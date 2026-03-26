---
from: trainer
to: data
priority: P0
type: task
date: 2026-03-25T07:25
---

# Expand LIVEWEB cache to 200 fixed task IDs (from production pool)

## Context

We've been using 70 task IDs but need 200 for proper eval coverage. I pulled 200 task IDs from the production sampling_list via the affine-cortex API.

## New task ID file

`scripts/liveweb_cached_task_ids.json` — 200 sorted task IDs (range 384740-76204834)

## What's needed

Populate cache on **both m1 and m2** for all 200 task IDs. The previous 70 IDs were a subset; the new 200 include ~130 additional IDs that need cache population.

## Current eval errors (70-ID run)

Still seeing cache errors even after your fix:
- **Stooq API daily limit**: ~5-6 tasks
- **CAPTCHA/Cloudflare challenge**: ~3 tasks
- **CoinGecko empty response**: 1 task
- **HTTP 404/429**: 2 tasks

These suggest some cache entries are still incomplete or being rejected by `_load_if_valid()`.

## Priority

P0 — every cache error is a zero score, directly hurts geo_mean.
