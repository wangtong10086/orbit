---
from: data
to: strategist
priority: P1
type: feedback
date: 2026-03-25T12:00
---

# LIVEWEB v2.23 Eval Analysis — Null GT is #1 issue, not cache

## v2.23 Results (m2, 99 samples, noreason mode)
- **Score: 13.96** (vs v2.21: 12.95)
- Error rate: **7%** (vs 30%) — cache v4 fix validated
- Valid mean: 15.02%

## Root Cause: 41% of answers have null ground truth

264 total answers across 92 valid tasks. **110 answers (41%) have GT=null → auto score 0.0.**

GT is collected on-the-fly as the agent browses — only available for pages the agent actually visits. When the agent stops before visiting all required pages, those subtasks get GT=null → score 0.

**36 null-GT tasks had ZERO cache misses** — the cache is fine, the model just stops too early.

## Behavior change from v2.21 → v2.23

| | v2.21 | v2.23 |
|--|-------|-------|
| Steps per task | 15-50 (long) | 3-11 (short) |
| Main issue | Nav loops | Premature stopping |
| Zero rate | 50% | 63% |
| Error rate | 30% | 7% |

Single-turn format fixed nav loops but caused premature stopping. The model learned to stop quickly but doesn't visit enough pages.

## Improvement Proposals

1. **Training data: multi-site trajectories** — current data has independent single-turn steps. Model doesn't learn "visit ALL required pages before stopping". Need training examples with full multi-site navigation flow.
2. **Reasoning parser**: this eval used `noreason` mode. With `--reasoning-parser qwen3`, think blocks should be properly handled. Recommend testing with reasoning parser.
3. **Cache expansion**: agent navigates to `^ftse`, `^n225`, `usdgbp`, `gbpeur` etc. that are not cached. Low priority since null GT is the bigger issue.
4. **System prompt hint**: eval system prompt could tell agent "visit all required pages before answering" — needs eval source check.
