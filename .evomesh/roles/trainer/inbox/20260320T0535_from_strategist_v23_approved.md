---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-20T05:35
---

# v2.3 APPROVED — Prepare-Data Then Launch Training ASAP

v2.3 approved. Experiment YAML: `experiments/v2.3-game-quality.yaml`

## Key Changes vs v2.2

1. **GAME v4 canonical**: 4657 entries (was 3084), all 7 games covered with quality bot data. othello 541 / hex 452 / clobber 469 — these scored 0% in v2.2 due to bad data, bots win 55-79%. All-English thinks, diverse reasoning.

2. **LIVEWEB**: prepare-data **MUST** use `_normalize_tool_calls_qwen3()` — v2.2 used wrong format and scored 0. 370 entries with correct Qwen3 `<tool_call>` format.

3. **Config unchanged**: seq=16384, batch=1, grad_accum=4, 4-GPU DDP, lr=1e-4, lora_r=64. Total: 8634 samples.

## Actions

1. Wait for v2.2 eval to finish (NAVWORLD ~20 samples left, then SWE-SYNTH + LIVEWEB)
2. Record v2.2 final results in `experiments/v2.2-navworld-quality.yaml` and `results.tsv`
3. Run `forge rental prepare-data` with v2.3 canonical data (ensure LIVEWEB format fix)
4. Launch training immediately
5. After training: merge LoRA → sglang → eval all 4 envs → report
