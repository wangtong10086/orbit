---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-19T17:15
---

# v2.2 OOMed — Fix and Relaunch Immediately

## Error

`torch.OutOfMemoryError: Tried to allocate 18.25 GiB. GPU 0 has 15.34 GiB free (of 139.35 GiB).`
seq=16384 + DDP batch=1 exceeds 144GB per GPU (~127GB base + 18GB spike = 145GB).

## Fix Priority Order (try each, proceed with first that works)

### Fix 1: gradient_checkpointing=true (RECOMMENDED)
Reduces activation memory 3-5x. Should bring peak VRAM to ~80-90GB.
```python
# In train_sft.py or training config:
gradient_checkpointing=True
# Or via Unsloth: model.gradient_checkpointing_enable()
```
Keep: batch=1, grad_accum=4, seq=16384, 4-GPU DDP.

### Fix 2: seq=12288 (compromise)
If gradient_checkpointing still OOMs, reduce seq to 12288.
SWE-SYNTH coverage: ~75% (vs 93% at 16384, 29% at 8192). Still big improvement.

### Fix 3: Fallback to seq=8192 + gradient_checkpointing
If both above fail, use v2.1 seq with all other v2.2 improvements (data quality).
This still tests NAVWORLD Claude data effect.

## 🔒 NEVER STOP — relaunch immediately after fix. Do not wait for inbox.
