---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-28T04:00
---

# v2.28 — 切换到 ms-swift 框架，停止自写脚本

## 停止当前方案
自写的 `train_full_sft_v2.py` 存在 loss masking、tool call 处理、chat template 等潜在 bug。竞争对手使用 ms-swift 4.0.2，我们也切换。

## 新方案：ms-swift

### 安装
```bash
pip install ms-swift[llm]>=4.0
```

### 训练命令（参考竞争对手配置）
```bash
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 \
swift sft \
  --model Qwen/Qwen3-32B \
  --model_dir /root/models/Qwen3-32B \
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
  --save_steps 50 \
  --save_total_limit 5 \
  --logging_steps 10 \
  --output_dir /root/checkpoints \
  --torch_dtype bfloat16
```

### 数据
- `/root/data/combined.jsonl` — 87332 条，已过滤，直接使用
- ms-swift 原生支持 messages 格式 + tool_calls，自动处理 loss masking
- 如果 ms-swift 数据格式不兼容，查文档调整 `--dataset_format`

### 关键配置
- per_device_batch_size=1, grad_accum=4 (effective=32) — 比我们之前的 2×2 更保守，匹配竞争对手
- ms-swift 自动处理 chat template、tool_calls、loss masking
- ZeRO-3 已验证可用（74GB/143GB per GPU）

### 注意
- 先 `swift sft --help` 确认参数名
- ms-swift 的数据格式可能需要 `messages` 字段在顶层（我们的数据已经是这样）
- 如果有 `tools` 字段需求，检查 ms-swift 文档
- 机器：m3, `forge remote -m m3`
