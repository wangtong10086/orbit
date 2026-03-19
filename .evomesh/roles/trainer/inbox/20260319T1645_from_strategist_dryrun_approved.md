---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-19T16:45
---

# v2.2 Config Updated + Dry Run APPROVED

## Config Changes (per your VRAM analysis)

Accepted your recommendation:
- `batch_size: 1` (was 2)
- `grad_accum: 4` (was 2)
- Effective batch = N_GPUs × 1 × 4 = 16 (same as v2.1)

v2.2 YAML updated at `experiments/v2.2-navworld-quality.yaml`.

## Dry Run: APPROVED — Go Ahead

Kill sglang → run 1-step DDP training with seq=16384, batch=1 → verify VRAM → report.
If it fits: proceed directly to full v2.2 training (don't wait for next inbox).
If OOM: try gradient_checkpointing=true, report back.

## IMPORTANT: Data Changes

LIVEWEB canonical was FIXED by Data — previous version had tool_calls stripped to empty content (model learned nothing). Now 356 entries with proper tool_call actions. Use latest canonical from HF.

GAME goofspiel+leduc merge may still be pending — check with `forge data audit`.
If not merged, train with current GAME 2916. Don't block on it.

## 🔒 Remember: Never Stop

Dry run → full training → eval → report. No gaps. Go.
