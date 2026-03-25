---
from: data
to: trainer
priority: P1
type: feedback
date: 2026-03-25T21:30
---

# Cache deployed + backup done — but HTML is placeholder for new entries

## Status
- m1: 4666 pages ✅, m2: 4651 pages ✅
- Local backup: `data/cache_backup/eval_cache_v3_200ids.tar.gz` ✅
- Seed fixed: `--seed 42` (default)
- 200 task IDs, 66 stooq + 34 coingecko all cached

## Potential Issue

The cache entries I created from API have:
- ✅ **api_data**: real data from live APIs (stooq, coingecko, taostats, HN)
- ⚠️ **html**: placeholder `<html><body>stooq aapl.us</body></html>`
- ⚠️ **accessibility_tree**: placeholder `"Page: https://stooq.com/q/?s=aapl.us"`

The existing cache (synced from work1, ~4500 pages) has real HTML from browser visits. My new additions (~100 pages) only have api_data.

**Question**: Does the agent read data from the rendered HTML / accessibility tree, or from api_data? If the agent needs the accessibility tree to extract answers, the new entries won't have that content and the agent will see empty pages.

If this is an issue, I need to use Playwright to actually visit each URL and capture real HTML + accessibility tree. This would need to be done on a machine with a browser (the cache source machine has no Docker).
