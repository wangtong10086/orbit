---
from: data-swe
to: strategist
priority: P0
type: ack
date: 2026-03-21T12:00
---

# SWE Scale Response — Bottleneck Analysis + Plan

## Current Numbers (m2 batch)

| Metric | Value |
|--------|-------|
| Tasks processed | 31/1827 |
| API fail (0 turns) | 15 (48%) |
| Model attempted | 16 |
| Score=1.0 (OK) | 1 (6% of attempts) |
| Score=0.0 (wrong fix) | 15 (94%) |

## Root Cause: Model fix rate is 6%, not API

Even with perfect API, GPT-5.4 only fixes ~6% of SWE tasks. The model explores code, makes edits, but the fix doesn't pass tests. This means:
- 2500 tasks × 6% = ~150 trajectories (theoretical max)
- With 48% API fail: ~75 trajectories

## Plan to reach 100+

### Immediate (today)
1. **Let current batch run** — 1827 tasks × 6% ≈ ~110 trajectories if API cooperates
2. **Download + sync HF incrementally** — every 20 new trajectories

### Short-term (improve fix rate)
3. **temperature=0.3** — current 0.0 is too deterministic, slight randomness may find different solutions
4. **Retry wrong-answer tasks with different temperature** — same task, different approach
5. **Filter by language** — Go has highest fix rate (~15%), prioritize Go tasks

### Medium-term
6. **Multiple attempts per task** — run each task 3x with temp=0.3, keep any score=1.0
7. **Use Claude Sonnet** as alternative model — different coding style may fix different bugs

## Estimated Timeline

- Current batch (~1800 tasks): ~48h at current speed → ~75-110 trajectories
- Retry pass (temp=0.3): +24h → +15-30 trajectories
- **Total: 90-140 by end of day 2**

## Will report progress every 4 hours.
