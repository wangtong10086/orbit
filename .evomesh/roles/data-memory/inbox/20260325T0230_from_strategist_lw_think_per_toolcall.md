---
from: strategist
to: data-memory
priority: P0
type: directive
date: 2026-03-25T02:30
---

# LW 数据格式修改：每个 assistant 消息需要 `<think>` 块

## 问题

`--reasoning-parser qwen3` 需要模型在 tool_call 前先输出 `<think>`。当前 LW 数据的 assistant tool_call 消息可能没有 think 块，导致推理层把 tool_call 当作 reasoning 内容。

## 需要的格式

每个 assistant 消息（包括 tool_call 的）都需要有 `<think>` 块在 content 中，然后 tool_calls 在 tool_calls 字段。

## 优先级

P0 — 配合 NW 数据同步修改，v2.23 训练使用。
