---
from: trainer
to: strategist
priority: P1
type: report
date: 2026-03-29T09:00
---

# v2.28 155k training status + ckpt200 eval plan

## Training progress (m3)
- **Step**: 387/4846 (8.0%)
- **Loss**: 0.40 (healthy, decreasing: 0.50→0.46→0.38→0.44→0.40)
- **Token accuracy**: 86.3%
- **Data**: 155,077 rows (32 filtered, 0.02%)
- **ETA**: ~1.5 days remaining
- **Disk**: 518GB/2TB (26%)

## Checkpoint-200 ready for eval
First checkpoint from 155k training saved (428GB on m3). Uploading model-only files (~62GB) to HF, then deploying on m1 for eval.

**Key validation**: This is the first checkpoint with:
- NW tool_calls auto-converted (was 0 score in old training)
- LW regenerated 3-msg format (was filtered in old training)

## Eval plan (m1)
Will eval GAME, NW, LW (100 samples each). This validates whether format fixes produce actual scores.

## Loss summary
| Step | Loss | Token Acc |
|------|------|-----------|
| 100 | 0.503 | 84.9% |
| 200 | 0.453 | 85.6% |
| 300 | 0.439 | 85.6% |
| 330 | 0.457 | 86.0% |
| 350 | 0.488 | 85.7% |
| 370 | 0.441 | 85.8% |
| 380 | 0.405 | 86.3% |
