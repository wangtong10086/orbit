---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-28T06:00
---

# v2.28 数据确认 — 环境就绪后立即启动

## 数据
87382 条，Strategist 会上传 combined.jsonl 到 m3。

| Env | 条数 |
|-----|------|
| GAME | 38663 |
| MemoryGym | 20000 |
| LW | 17108 |
| NW | 10006 |
| SWE-I | 1605 |
| **总计** | **87382** |

## ms-swift 训练配置
```
swift sft \
  --model /root/models/Qwen3-32B \
  --dataset /root/data/combined.jsonl \
  --train_type full \
  --deepspeed zero3 \
  --max_length 32768 \
  --per_device_train_batch_size 1 \
  --gradient_accumulation_steps 4 \
  --learning_rate 2e-5 \
  --lr_scheduler_type cosine \
  --warmup_ratio 0.03 \
  --weight_decay 0.01 \
  --max_grad_norm 1.0 \
  --num_train_epochs 1 \
  --bf16 true \
  --gradient_checkpointing true \
  --save_steps 100 \
  --save_total_limit 5 \
  --logging_steps 10 \
  --output_dir /root/checkpoints \
  --torch_dtype bfloat16
```

## 关键教训（上次崩溃原因）
1. **训练时绝不上传 HF** — 上次 5×400GB 上传导致 m3 崩溃
2. **save_steps=100**（非50）— checkpoint 428GB，减少保存开销和磁盘压力
3. **训练完成后再统一上传 checkpoints**

## 环境就绪后
1. 通知 Strategist 数据路径（可能是 /data/ 或 /root/data/）
2. Strategist 上传 combined.jsonl
3. 启动训练
