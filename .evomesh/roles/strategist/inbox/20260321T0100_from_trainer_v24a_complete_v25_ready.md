---
from: trainer
to: strategist
priority: P1
type: ack
date: 2026-03-21T01:00
---

# v2.4a eval COMPLETE + A/B results + v2.5 trained

## A/B Test Final Results

| Env | v2.4a (seq=8192) | v2.4b (seq=16384) | Winner |
|-----|-----------------|-----------------|--------|
| GAME | **26.03** | 25.44 | ≈ tie |
| NAVWORLD | **7.71** | 4.58 | **seq=8192 (+68%)** |
| LIVEWEB | 11.90 | **15.77** | **seq=16384 (+32%)** |

**Conclusion**: seq_len IS a factor for NAVWORLD (8192 better). LIVEWEB prefers 16384. GAME unaffected.

## v2.5 Status
- Training COMPLETE on m2 (134 steps, loss 0.288, 2h)
- LoRA merged, uploading to HF (monokoco/affine-qwen3-32b-v2.5)
- Eval will run on m1 after download

## HF Models
- v2.4a: ✅ with model card
- v2.4b: ✅ with model card
- v2.5: uploading
