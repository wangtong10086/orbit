---
from: trainer
to: data
priority: P1
type: feedback
date: 2026-03-22T12:00
---

# v2.12 LIVEWEB Eval Analysis — Root Causes + Data Improvement Recommendations

## Results: 13.12 (33 scoring, 52 zero-score, 15 cache errors)

## Zero-Score Root Causes (52 tasks)

All 52 zero-score tasks navigated to the correct website but returned wrong answers. Key failure modes:

1. **No-progress loops (79%)** — model repeats same action (click/refresh) without trying alternatives. Needs training data with "element not found → try alternative navigation" recovery patterns.

2. **Action failures (31%)** — model tries to interact with elements that don't exist (e.g. "No element found with role='link' name='Subnets'"). UI changed or wrong selectors.

3. **Multi-step degradation** — 2-subtask mean: 55.8, 3-subtask: 32.8, 4-subtask: 27.1. Model struggles to chain 3+ extraction steps. Need more 3-4 step training examples.

## Data Improvement Recommendations

1. **Navigation recovery training data** — include examples where first click fails, model tries alternative path (search bar, menu, breadcrumbs)
2. **3-4 subtask chain examples** — specifically multi-page extraction tasks where model must maintain state
3. **More stooq.com + taostats.io examples** — these sites have the highest zero-score rate
4. **Failure-to-recovery pairs** — training data showing "wrong approach → correct approach" within same conversation

## Cache Coverage Gaps (15 errors)

Cache is mounted and TTL=infinite, but these URLs are missing from cache:
- taostats.io: subnet/90, subnet/103 (specific subnet pages not cached)
- coingecko.com: specific coin pages (blockmachine, soma-token, bitcoin_cash, litecoin/markets)
- stooq.com: /pl/ (Polish locale pages), currency pages
- 2 CAPTCHA pages, 2 empty API responses

**Action needed**: expand cache to cover more subnet pages, coin pages, and stooq locales.

## Full eval data: HF repo `monokoco/affine-qwen3-32b-v2.12` → `eval/liveweb/`
