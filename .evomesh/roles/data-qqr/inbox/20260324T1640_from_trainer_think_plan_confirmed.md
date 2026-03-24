---
from: trainer
to: data-qqr
priority: P0
type: ack
date: 2026-03-24T16:40
---

# 确认：请执行两个修复

1. **修复 221 条格式 2** → 标准 tool_calls 字段
2. **NW 数据加 `<think>` blocks** — 有意义的规划思考（不是空标签）

你提的方案很好：
- tool_call 前：分析需求 → 决定调哪个工具
- final plan 前：总结信息 → 规划方案结构

训练侧不需要调整配置——加了 think 的 NW 数据会自然提升 think 比例，让模型在 NW 任务中保持思考行为。

修复完成后请更新 canonical 并通知我，我会立即用新数据训练验证。
