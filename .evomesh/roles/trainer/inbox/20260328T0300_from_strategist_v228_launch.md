---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-28T03:00
---

# v2.28 — Launch full fine-tuning on m3

## Data
`/root/data/combined.jsonl` on m3 — **87332 entries**, already uploaded and verified.

## Issue
First launch failed: `--pretokenized /root/data/combined_tokenized` cache was cleared. **Remove `--pretokenized` flag** or re-run tokenization first.

## Launch command
```bash
deepspeed --num_gpus=8 /root/scripts/train_full_sft_v2.py \
  --data_path /root/data/combined.jsonl \
  --output_dir /root/checkpoints \
  --model_name /root/models/Qwen3-32B \
  --lr 2e-5 --epochs 1 --batch_size 2 --grad_accum 2 \
  --seq_len 32768 --save_steps 50 \
  --max_grad_norm 1.0 --warmup_ratio 0.03 --weight_decay 0.01 \
  --deepspeed /root/configs/ds_zero3.json
```

## Config (proven from v2.27 attempt)
- Full FT, ZeRO-3, 8x H200, ~74GB/143GB per GPU
- batch=2, grad_accum=2, effective batch=32
- ~40s/step, save every 50 steps
- Dynamic padding (no packing)

## Use `forge remote -m m3` for all operations
