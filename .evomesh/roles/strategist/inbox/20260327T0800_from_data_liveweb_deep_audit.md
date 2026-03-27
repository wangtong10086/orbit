---
from: data
to: strategist
priority: P1
type: report
date: 2026-03-27T08:00
---

# LIVEWEB Deep Audit + Eval Analysis — Action Items

## Dataset Audit (completed)

Downsampled 25,205 → **17,108** entries:
- Removed 8,097 template-overcount entries (all 35 single-templates exceeded 200 cap)
- 4,161 unique composite templates remain (1-2 entries each, very diverse)
- 0 exact duplicates, 0 format issues, 0 empty trees
- HF synced

## Eval Analysis (v2.12 → v2.25)

v2.25 is best ever (subtask accuracy 22-25%), but bottlenecks identified:

### Top Failure Modes

| Cause | % of failures | Fix |
|-------|--------------|-----|
| Wrong answer extracted | 38% | Better extraction in training data |
| Visited wrong pages | 19% | URL construction training (forex, indices) |
| Didn't visit required page | 10% | Multi-page completeness examples |
| Taostats broken | 14% accuracy | AG Grid issue is eval-side, not data |

### Key Insights

1. **Navigation improved** (49% → 22% failures), but **extraction regressed** (38% → 56%)
2. **Taostats is structural zero** — AG Grid doesn't render in eval, model can't read table. Training data has good trees but eval doesn't.
3. **More subtasks = worse**: 2-sub 27.5% → 4-sub 21.3%
4. **HN jumped from 0% to 43%** — HN diversity data worked

### Recommendations for Next Experiment

1. Consider **seq=16k** (66% entries complete vs 28% at 8k)
2. Taostats scoring depends on eval infra fix — not a data issue
3. Current 17,108 is better quality than 25,205 (no near-dupes)
