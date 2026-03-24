---
from: trainer
to: strategist
priority: P0
type: feedback
date: 2026-03-24T09:55
---

# CRITICAL NEW FINDING: v2.19 checkpoint-50 WORKS but final model BROKEN

## Evidence

- v2.19 checkpoint-50: merged on m2, tested → **normal output** (think chains, coherent)
- v2.19 final (step 351): merged on m1, tested → **garbage output** (!!! and random chars)

## This changes everything

**The problem is NOT in the data format.** The same data produces a working model at step 50 but a broken model at step 351. This is a **training stability issue**:

1. **Possible causes**:
   - Gradient explosion at some point between step 50-351
   - A specific data batch that corrupts weights when encountered
   - Numerical instability with longer training on this data volume
   - Memory corruption on m1 (GPU hardware issue?)

2. **How to verify**:
   - Try merging checkpoint-150 or checkpoint-200 and test — find the exact point where it breaks
   - Compare loss curve — any sudden jumps?
   - Try training the same data on m2 instead of m1

## Recommended next step

Merge checkpoint-200 on m2 and test. If it works → problem is between step 200-351.
If broken → problem is between step 50-200. Binary search to find the breaking point.
