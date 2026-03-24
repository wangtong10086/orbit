---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-24T07:15
---

# v2.19 APPROVED — Launch immediately

v2.18 was corrupted (model outputs garbage `!!!!`). Same config worked in v2.13b-v2.17a, likely random event. Retry with latest data.

## Data

Use ALL current canonical files:
- `data/canonical/game.jsonl` (6086)
- `data/canonical/navworld.jsonl` (1692)
- `data/canonical/liveweb.jsonl` (2345)
- `data/canonical/swe_infinite.jsonl` (594)
- **Total: 10717**

Combine: `cat data/canonical/game.jsonl data/canonical/navworld.jsonl data/canonical/liveweb.jsonl data/canonical/swe_infinite.jsonl > combined.jsonl`

## Pre-Training Validation (MANDATORY)
1. `python3 -c "import json; [json.loads(l) for l in open('combined.jsonl')]"` — no errors
2. Check content=None: must be 0
3. Verify line count = 10717

## Config (SAME as all successful runs)
- lr=5e-5, seq=8192, epochs=1, batch=2, grad_accum=2
- lora_r=64, lora_alpha=128
- packing=true, DDP, all GPUs

## IMPORTANT
- Kill gin_rummy generation processes first (`pkill -f generate_fast`)
- Kill old sglang before training
- Upload model to HF IMMEDIATELY after training (don't lose it like v2.13b)

## Post-Training: Full 7-step process
1. Merge + HF upload
2. AMAP key verify
3. 3-sample sanity check — **if model outputs garbage again, STOP and report**
4. Full 100-sample eval (GAME + NW + LW + SWE-I)
5. Save eval files + upload HF
6. Formal analysis report
7. Update results.tsv
