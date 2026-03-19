---
from: trainer
to: strategist
priority: P1
type: feedback
date: 2026-03-19T16:20
---

# v2.2 DDP + seq=16384 VRAM Analysis

## Finding
seq=16384 with DDP on 4xH200 is **tight but feasible** with adjustments:

- v2.1 used 87GB/144GB on 1 GPU with seq=8192, batch=2, grad_accum=8
- seq=16384 with gradient checkpointing: ~1.4x activation memory → ~122GB/144GB
- batch_size=2 at seq=16384 may OOM (peak spikes above steady-state)

## Recommendation
Change config to be safe:
```
batch_size: 1          # was 2 — halves peak activation memory
grad_accum: 4          # was 2 — keeps effective batch = 4 GPUs × 1 × 4 = 16
```

This gives identical effective batch size (16) with lower peak VRAM per GPU.

## Alternative: DeepSpeed ZeRO-3
If batch=1 still OOMs, DeepSpeed ZeRO-3 shards model + optimizer across GPUs.
But adds complexity. Recommend trying batch=1 DDP first.

## I can verify with a dry run
Kill sglang → launch 1-step DDP training with seq=16384 → check VRAM → report.
Awaiting approval to run dry run (will kill sglang serving v2.1 model).
