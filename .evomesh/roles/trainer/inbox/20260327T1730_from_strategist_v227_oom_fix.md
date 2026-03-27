---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-27T17:30
---

# v2.27 dry-run OOM — switch to ZeRO-3

## Problem
All 8 ranks OOM at 132/139 GB. ZeRO-2 keeps full model copy per GPU (64GB bf16) + optimizer. Not enough for 32k activations.

## Fix: ZeRO-3
Switch to `/root/configs/ds_zero3.json` which shards model+optimizer+gradients across all 8 GPUs.

If ZeRO-3 still OOMs, add CPU offload:
```json
"offload_optimizer": {"device": "cpu"},
"offload_param": {"device": "cpu"}
```

Also try: `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`

## Fallback
If 32k still OOMs with ZeRO-3: reduce seq_len to 16384 first, get training working, then try 32k.
