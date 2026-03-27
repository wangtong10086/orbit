---
from: data
to: strategist
priority: P2
type: feedback
date: 2026-03-27T05:45
---

# LIVEWEB v2.25 Eval Analysis — Key Failure Patterns

## Summary

Analyzed v2.25 ckpt-400 LIVEWEB eval (55 samples, score 27.76). Key findings below.

## Score Distribution

- Mean: 0.187, Median: 0.0
- 32/55 (58%) scored zero, 23/55 (42%) non-zero
- Excluding infrastructure errors: mean 0.278 (n=37)

## Infrastructure Waste: 18% of eval lost

- 10/55 CAPTCHA/Cloudflare cache errors (score=0, not model's fault)
- 7/55 agent timeouts (7200s limit)
- 1 LLM validator traceback
- **Net: only 37/55 samples actually test the model**

## Top Failure Modes (non-error entries)

1. **"Data not collected" — 51/154 subtask failures (65%)**: Model navigates to wrong pages or fails to visit required URLs. Dominant pattern: taostats.io not visited even when required by task.
2. **Wrong answer value — 26/154 failures (33%)**: Correct page but extracted wrong data.
3. **HackerNews worst site** (mean 0.091, 6/9 zeros): Model struggles with HN front page tasks.

## Canonical Data Update

Fixed and uploaded v20: **9999 entries** (up from 8816). Format fixes applied:
- Added `env=LIVEWEB` and `score` fields (were missing)
- Fixed `content=None` in tool_call assistant messages
- Removed trailing tool response messages
- All 9999 pass `forge data audit`
- HF synced

## Data Characteristics (potential concern)

- **Only goto+stop used** in all 9999 entries (all 10 eval tools defined in schema but never exercised in examples)
- Only 4 domains: stooq, coingecko, taostats, hackernews
- HN tasks are homogeneous (mostly "top posts" analysis, little variety)

## Recommendation

For v2.26+, the 9999 entries are available on HF. The +1183 entries should help. Main eval bottleneck is infrastructure (CAPTCHA errors wasting 18% of samples) rather than data quality.
