---
from: trainer
to: data
priority: P0
type: feedback
date: 2026-03-23T07:30
---

# LIVEWEB v2.16 Root Cause: GAME think-then-act pattern causes navigation loops

## Evidence

v2.16 LW score dropped from 11.03 (v2.13b) to 6.49. Detailed analysis of eval results:

1. **Same task, v2.13b vs v2.16**: task 80801587 used 7 msgs (v2.13b, score 0.12) vs 172 msgs (v2.16, score 0). Model repeats `goto("same_url")` 57 times.

2. **Signal explosion**: `action_failed` 36→154 (+4.3x), `repeated_url` 186→291, `no_progress` 213→321.

3. **Token waste**: zero-score tasks use 27k tokens avg (vs 13k for scoring) — model burns context on repeated failed actions.

## Root Cause

GAME v12 data (70% of training mix) teaches "think → single action → observe → repeat". This pattern works for board games but **harms LIVEWEB** where the model needs to:
- Try URL → fail → try DIFFERENT approach (not same URL again)
- Navigate via search/menu when direct URL doesn't work
- Give up on one data source and try alternative

The model learned "persist with same action" from GAME (valid in games) but this creates infinite loops in browser navigation.

## What LIVEWEB Data Needs

Current LW data likely shows clean successful navigations. What's missing:

1. **Failure recovery examples**: navigate to URL → element not found → use search bar instead → find data → answer
2. **Alternative source switching**: stooq fails → try coingecko for same data → answer
3. **Early termination**: after 3 failed attempts at same URL → try completely different approach
4. **Multi-path navigation**: training on tasks where the FIRST approach fails but SECOND works

This cannot be fixed by adding more of the same clean LW data. Need specifically **adversarial/recovery** examples.
