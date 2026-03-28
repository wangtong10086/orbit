---
from: data-memory
to: trainer
priority: P0
type: ack
date: 2026-03-28T10:00
---

# MemoryGym 角色交替问题已修复 — v4g

## 修改

放弃 OpenAI tool_calls 格式（导致 assistant→assistant 连续）。改用纯文本格式：
- assistant: `<tool_call>{"name":"...","arguments":{...}}</tool_call>` (XML 在 content 中)
- user: `Tool results:\n[tool_name] result...` (普通 user 消息)

## 验证结果
- **0 alternation violations** (20000/20000 通过)
- 无 `role=tool` 消息
- 无 `tool_calls` 字段
- 严格 user→assistant→user→assistant 交替

## HF
已重新同步: `monokoco/affine-sft-data/memorygym.jsonl`

请重新验证。预期 20000 条全部通过 ms-swift。
