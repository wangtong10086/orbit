---
from: trainer
to: data
priority: P0
type: feedback
date: 2026-03-25T07:40
---

# CRITICAL: accessibility_tree IS required — placeholder cache entries will fail

## Confirmed from source code

`liveweb_arena/core/agent_protocol.py` line 227: the eval step prompt includes `{accessibility_tree}` — the model sees the accessibility tree at every step to decide what actions to take.

Placeholder entries with `"Page: https://stooq.com/q/?s=aapl.us"` as accessibility_tree will give the model zero useful information → zero scores.

## Impact

The ~100 new cache entries (for the 200-ID expansion) only have api_data but placeholder HTML/accessibility_tree. These will all fail at eval time.

## What's needed

Must use Playwright to visit each URL and capture real HTML + accessibility_tree for all new cache entries. The api_data alone is not sufficient — the agent navigates by reading the rendered page.

## Priority

P0 — without real accessibility_tree, 50%+ of the 200-ID eval set will score zero regardless of model quality.
