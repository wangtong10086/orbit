# v2.12 LIVEWEB Eval Analysis

> Status: Archived evaluation report
> Authority: Non-normative
> Last reviewed: 2026-04-04
> Use this file as a historical result record, not as a current specification.


## Summary
- **Score: 13.12** (mean=0.1312, 100 samples)
- Scoring tasks: 33/100 (33%)
- Zero-score tasks: 52/100 (52%)
- Errors (infra): 15/100 (15%)

## Why It Scores (33 tasks)

The model scores when it can:
1. **Navigate to the correct page** and extract data from familiar sites (coingecko, taostats)
2. **Answer simple 2-subtask questions** — 2-subtask mean: 55.8 (vs 3-subtask: 32.8, 4-subtask: 27.1)
3. **Use minimal tokens** — shorter conversations tend to get correct answers (less chance to go off track)

Top scoring pattern: model goes to correct URL → reads page data → formats answer correctly.

## Why It Doesn't Score — ROOT CAUSES (52 zero-score tasks)

### Root Cause 1: Wrong Answers Despite Navigation (52/52 = 100%)
Every single zero-score task reached the website but returned the **wrong answer**. The model navigates but fails to extract/compute the correct data. This is not a format issue — it's a comprehension/extraction issue.

### Root Cause 2: No Progress / Stuck Loops (41/52 = 79%)
The model gets stuck repeating actions without making progress. The `no_progress` signal fires when the model:
- Clicks the same element repeatedly
- Refreshes the page without trying something new
- Gets trapped in navigation loops

### Root Cause 3: Action Failures (16/52 = 31%)
`action_failed` signals indicate the model tries to click/interact with elements that don't exist or aren't accessible:
- "No element found with role='link' name='Subnets'" — wrong selector
- Elements have changed names or aren't visible in the current viewport

### Root Cause 4: Multi-Subtask Scaling
Performance degrades sharply with more subtasks:
- 2 subtasks: 46% score rate (13/28 tasks score)
- 3 subtasks: 26% score rate (8/31 tasks score)
- 4 subtasks: 46% score rate (12/26 tasks score, but lower mean)

The model can handle 1-2 navigation+extraction steps but struggles to chain 3+ correctly.

### Root Cause 5: High Token Usage on Failures
- Zero-score tasks average 38,788 tokens (still consuming lots of context)
- Scoring tasks average 46,114 tokens
- Model doesn't fail fast — it keeps trying until timeout, wasting context window

## Infrastructure Errors (15 tasks)

| Domain | Count | Cause |
|--------|-------|-------|
| coingecko.com | 5 | HTTP 404 (page URL changed) |
| stooq.com | 4 | HTTP 404 (URL structure change) |
| CAPTCHA | 2 | Cloudflare challenge page |
| taostats.io | 2 | HTTP 404 (subnet page gone) |
| other | 2 | Empty API response |

These are cache misses — the cached page URLs no longer exist on the live site.

## Recommendations for Data Improvement

1. **More diverse navigation patterns** — training data should include recovery from wrong clicks, alternative navigation paths
2. **Multi-step extraction training** — specifically train on 3-4 subtask chains where model must maintain state across pages
3. **Failure recovery examples** — train on "element not found → try alternative approach" patterns instead of repeating
4. **Stooq/Taostats-specific data** — these sites have the most zero scores; need more training examples with their specific UI patterns
5. **Update LIVEWEB cache** — 15% error rate from stale cache; refresh cached pages for URLs that return 404
