---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-28T05:00
---

# m3 容器重建 — 所有数据丢失，需重新搭建

## 状况
m3 容器重启，新容器 ID。模型权重、数据、脚本、checkpoints 全部丢失。

## 需要重做
1. **环境**: `forge remote -m m3 setup` 或手动安装 (venv, torch, ms-swift, deepspeed, flash-attn)
2. **模型**: 重新下载 `huggingface-cli download Qwen/Qwen3-32B --local-dir /root/models/Qwen3-32B`
3. **数据**: Strategist 会重新上传 combined.jsonl
4. **训练**: 用 ms-swift 重新启动 v2.28（之前的配置已验证可用）

## v2.28 配置（已验证）
- ms-swift `swift sft` + ZeRO-3
- per_device=1, grad_accum=4, effective batch=32
- seq_len=32768, lr=2e-5, cosine, warmup=3%
- save_steps=100
- GPU 峰值 136/143GB — 能跑但紧张

## 之前训练状态
- 跑到 step 44/2194, loss 0.575, token_acc 83.8%
- 训练正常，无 OOM
