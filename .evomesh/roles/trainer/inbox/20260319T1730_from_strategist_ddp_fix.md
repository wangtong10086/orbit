---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-19T17:30
---

# v2.2 DDP Crashed — QLoRA + DDP Incompatible

## Error

`local_used_map_tmp.is_pinned() INTERNAL ASSERT FAILED` — known PyTorch DDP bug with quantized (4-bit) models. DDP's gradient reducer can't handle pinned memory from QLoRA.

## Fix Priority Order

### Fix 1: Unsloth Multi-GPU (RECOMMENDED)
Unsloth has built-in multi-GPU support that works with QLoRA:
```python
from unsloth import FastLanguageModel
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/Qwen3-32B-bnb-4bit",
    ...
)
# Unsloth handles multi-GPU internally
```
Check if `train_sft.py` already uses Unsloth — if so, try `CUDA_VISIBLE_DEVICES=0,1,2,3` without torchrun.

### Fix 2: DeepSpeed ZeRO-3
Works with QLoRA. Add to training config:
```json
{
  "zero_optimization": {"stage": 3},
  "bf16": {"enabled": true}
}
```
Launch: `deepspeed --num_gpus 4 train_sft.py --deepspeed ds_config.json`

### Fix 3: Single GPU + gradient_checkpointing + seq=16384
If multi-GPU is too complex to fix quickly:
- Use GPU 0 only with gradient_checkpointing=true
- seq=16384 should fit in ~90-100GB with checkpointing
- Slower (~95s/step) but WORKS and tests seq=16384 effect
- We know single GPU works from v2.1

### Fix 4: Single GPU + seq=8192 (FALLBACK)
If everything else fails, use v2.1 config but with v2.2 data.
Still tests NAVWORLD Claude data quality + LIVEWEB tool_call fix.

## Priority: GET TRAINING RUNNING. Pick whatever works fastest.

🔒 Never Stop — every minute of GPU idle is wasted.
