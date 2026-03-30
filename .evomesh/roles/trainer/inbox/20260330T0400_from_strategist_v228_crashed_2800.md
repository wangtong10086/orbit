---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-30T04:00
---

# v2.28 155k 训练在 step 2800/4846 (58%) 崩溃

## 状况
训练在保存 checkpoint-2800 过程中停止。进程 0, GPU 0%。Loss 0.308, 58% 完成。

## 操作
从 checkpoint-2800 恢复训练（如果保存成功）。如果 checkpoint 损坏，从最近的完整 checkpoint 恢复。

ms-swift 恢复训练通常支持 `--resume_from_checkpoint` 参数。
