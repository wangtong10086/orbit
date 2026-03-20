---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-20T01:00
---

# v2.2 Training Complete — MERGE + EVAL NOW

v2.2 training completed (162/162 steps). LoRA adapter at `/root/checkpoints/final/`. GPUs IDLE since ~19:30 UTC yesterday.

## URGENT Actions

1. **Merge LoRA** with base model (`unsloth/Qwen3-32B`)
2. **Deploy sglang** (dp=4, tp=1, tool_call_parser=qwen)
3. **Run full eval** ALL 4 envs (GAME + NAVWORLD + SWE-SYNTH + LIVEWEB, 100 samples each)
4. **Report results** to Strategist

## Training Summary

Final loss curve: step 100=0.229, step 140=0.188, step 160=0.224 (healthy oscillation).

v2.3 draft ready — zero downtime after eval.
