---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-25T02:10
---

# 重新评测 v2.21 — 加 --reasoning-parser qwen3

v2.21 模型已在 HF (monokoco/affine-qwen3-32b-v2.21)。在 M2 上部署并重新评测。

## sglang 启动命令（关键修改）

```bash
python3 -m sglang.launch_server \
  --model monokoco/affine-qwen3-32b-v2.21 \
  --tokenizer-path Qwen/Qwen3-32B \
  --dp 4 --tp 1 --port 30000 \
  --tool-call-parser qwen \
  --reasoning-parser qwen3 \
  --host 0.0.0.0 \
  --disable-cuda-graph
```

**关键变化**: `--reasoning-parser qwen3`（启用 Qwen3 thinking 模式）

## 评测 4 环境

GAME + NW + LW + SWE-I，各 100 samples。增量保存。

## 预期

v2.21 之前结果（无 reasoning parser）:
- GAME: 24.92 → 可能 30+（think 提升决策）
- NW: 42.84 → 可能 45+（think 也改善 NW）
- LW: 4.83
- SWE-I: 首次评测

## 重要

- M1 继续跑 v2.22 训练，不要中断
- M2 部署 v2.21 + reasoning-parser 评测
- 这是验证 thinking 修复效果的关键实验
