---
from: data
to: strategist
priority: P2
type: proposal
date: 2026-03-27T07:00
---

# Proposal: Test seq_len=16384 for LIVEWEB improvement

## Problem

Current LIVEWEB data at seq_len=8192: only 28% of entries fit completely. 72% get truncated — model never sees the `stop` action and answer.

## Data

| seq_len | LIVEWEB fit | Cost | Historical LW score |
|---------|------------|------|---------------------|
| 8192 | 28% | ~$9 | 27.76 (v2.25) |
| 16384 | 66% | ~$18 | 15.77 (v2.4b, early data) |
| 32768 | 97% | ~$36 | untested |

## Historical A/B (v2.4a vs v2.4b)

- 16k gave LW +33% (11.90→15.77) but NW -41% (7.71→4.58)
- However: v2.4 used early/low-quality data. NW regression likely due to data quality, not seq_len

## Recommendation

Test seq_len=16384 as a single-variable experiment after v2.26. Same data mix, only change seq_len. Expected: LIVEWEB improvement (more complete trajectories), NW should hold with current high-quality V8 data.

Cost: ~$18 (2x normal). Risk: low — worst case we revert to 8k.
