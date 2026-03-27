---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-27T12:00
---

# v2.27 dry-run on m3 — validate full FT before real training

## Task
Run a dry-run of v2.27 full fine-tuning on m3 (8x H200) to validate the setup before real training.

## What's ready on m3
- Data: `/root/data/combined.jsonl` (46721 entries, 1.27GB, shuffled)
- Script: `/root/scripts/train_full_sft.py` (dynamic padding, no packing, assistant-only loss)
- Launch: `/root/scripts/launch_v227.sh` (full run) and `/root/scripts/launch_v227_dryrun.sh` (test run)
- Model: `/root/models/Qwen3-32B` (full bf16 weights)
- DeepSpeed: `/root/configs/ds_zero2.json` (ZeRO-2)
- SSH: `forge remote -m m3 exec "<cmd>"`

## Dry-run steps
1. Launch: `forge remote -m m3 exec "screen -dmS train bash /root/scripts/launch_v227_dryrun.sh"`
2. Monitor: `forge remote -m m3 exec "tail -20 /root/logs/train_v227_dryrun.log"`
3. Verify: model loads, tokenization completes, first 10-20 steps run without OOM
4. Check GPU memory: `forge remote -m m3 exec "nvidia-smi"`
5. If OOM: switch to ZeRO-3 (`/root/configs/ds_zero3.json`) or reduce batch_size
6. If OK: report back, then we launch real training with proper save_steps

## Key config (dry-run)
- batch_size=1, grad_accum=1 (minimal VRAM)
- seq_len=32768
- save_steps=999999 (don't save during dry-run)

## IMPORTANT
- Use `forge remote -m m3` for all operations (not raw ssh)
- This is FULL fine-tuning (NOT QLoRA) — first time, expect issues
- Report: VRAM usage per GPU, throughput (s/step), any errors
