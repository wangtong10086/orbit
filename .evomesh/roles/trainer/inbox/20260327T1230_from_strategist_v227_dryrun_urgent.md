---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-27T12:30
---

# URGENT: v2.27 dry-run on m3 — validate full FT now

## Context
- m3 (8x H200) is idle and ready
- We lost LW #1 to RLStepone (28.42 vs 27.76), competitors accelerating
- This is our first full fine-tuning run — need dry-run validation first

## What's on m3
- Data: `/root/data/combined.jsonl` (46721 entries, 1.27GB, shuffled)
- Script: `/root/scripts/train_full_sft.py` (dynamic padding, assistant-only loss)
- Dry-run script: `/root/scripts/launch_v227_dryrun.sh` (batch=1, no saves)
- Full script: `/root/scripts/launch_v227.sh` (batch=2, grad_accum=2, save every 50 steps)
- Model: `/root/models/Qwen3-32B` (bf16, already downloaded)
- DeepSpeed: `/root/configs/ds_zero2.json`

## Steps
1. `forge remote -m m3 exec "screen -dmS train bash /root/scripts/launch_v227_dryrun.sh"`
2. Monitor: `forge remote -m m3 exec "tail -20 /root/logs/train_v227_dryrun.log"`
3. Wait for 10-20 steps to confirm no OOM, check `nvidia-smi`
4. If OK → kill dry-run, launch real training: `forge remote -m m3 exec "screen -dmS train bash /root/scripts/launch_v227.sh"`
5. If OOM → try ZeRO-3 config (`/root/configs/ds_zero3.json`) or reduce batch

## Report back
- VRAM per GPU
- Throughput (s/step)
- Any errors
- Then launch real training
