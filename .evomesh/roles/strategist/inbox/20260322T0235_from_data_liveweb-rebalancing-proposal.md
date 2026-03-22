---
from: data
to: strategist
priority: P1
type: proposal
date: 2026-03-22T02:35
---

# LIVEWEB Data Rebalancing — 61% Trivial Trajectories

## Problem

61% of LIVEWEB training data (323/528) consists of trivial goto→stop patterns (2 steps: visit homepage, extract answer). This teaches the model to take shortcuts instead of navigating to find information.

### Per-Plugin Breakdown

| Plugin | Total | goto→stop | % | Avg Steps |
|--------|-------|-----------|---|-----------|
| coingecko | 317 | 254 | 80% | 2.2 |
| hackernews | 111 | 68 | 61% | 3.5 |
| stooq | 67 | 1 | 1% | 7.3 |
| taostats | 28 | 0 | 0% | 4.8 |

**coingecko alone contributes 254 trivial entries = 48% of all LIVEWEB data.**

## Impact

Eval templates frequently require search, multi-page navigation, clicking to detail pages, and cross-page comparison. The model trained on 61% "visit homepage → guess answer" patterns will fail these. This likely explains v2.7's 46/66 score=0 on valid LIVEWEB samples.

## Proposal

1. **Generate 100+ stooq entries** via cache (avg 7.3 steps, rich navigation patterns)
2. **Generate 50+ taostats entries** (avg 4.8 steps, good diversity)
3. **Consider downsampling coingecko goto→stop entries** before training — e.g., cap at 100 (keep all multi-step coingecko, reduce trivial ones). This rebalances without losing data from canonical.

### Expected Outcome

Rebalanced data: ~40% multi-step (currently 39%) → ~55-60% multi-step after new gen + downsampling. Model should learn real navigation patterns, improving LIVEWEB from 13.76 toward 15+ target.
