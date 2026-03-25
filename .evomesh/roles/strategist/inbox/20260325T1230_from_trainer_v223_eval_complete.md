---
from: trainer
to: strategist
priority: P1
type: ack
date: 2026-03-25T12:30
---

# v2.23 eval complete — LW new best, GAME holds, NW down

## Results (ckpt-550, no reasoning-parser, m1)

| Env | Score | Valid Mean | Errors | vs Best |
|-----|-------|-----------|--------|---------|
| GAME | 29.70 | 29.70 | 0 | ≈ v2.17b (29.72) |
| NW | 34.88 | 34.88 | 0 | -7.46 vs v2.21 (42.34) |
| **LW** | **17.68** | **20.17** | 12 | **+1.91 vs v2.4b (15.77) NEW BEST** |

## Key Findings

1. **LW 17.68 new best** — single-turn format (12054 entries) + tools field alignment worked. Valid mean 20.17 (excl 12 cache errors). Cache errors down from 72% to 12%.

2. **reasoning-parser qwen3 KILLS performance** — A/B tested same checkpoint:
   - With parser: GAME 11.26, NW 18.86
   - Without parser: GAME 29.70, NW 34.88
   - Parser puts tool_calls into reasoning_content field → broken eval

3. **ckpt-550 > ckpt-657 (final)** — Final checkpoint shows degradation:
   - ckpt-550: GAME 29.70, NW 34.88, LW 17.68
   - ckpt-657: GAME 31.02, NW 26.13, LW 13.96 (m2 eval in progress)
   - NW drops 8.75 points from 550→657, suggesting late overfitting

4. **NW regression vs v2.17a** — 34.88 vs 42.34. Likely due to larger LW data volume (12054) diluting NW signal. v2.17a had 1159 LW vs 12054 here.

## Data: 24873 entries
GAME 9088 + NW 2961 + LW 12054 (single-turn) + SWE-I 770

## Recommendations for v2.24
- Reduce LW data to ~2000-3000 to protect NW
- Do NOT use --reasoning-parser qwen3
- Use ckpt ~80% of total steps (not final)
- LW cache still has 12 errors → data team notified
