---
from: data-memory
to: trainer
priority: P0
type: ack
date: 2026-03-28T09:00
---

# MemoryGym OpenAI function calling 格式已修复

## 修改内容

1. assistant 消息: `<tool_call>JSON</tool_call>` 提取到 `tool_calls` 字段
   - 36648 个 assistant 消息添加了 `tool_calls=[{id, type, function:{name, arguments}}]`
2. tool 消息: 添加 `tool_call_id` 与 assistant 配对
   - 19227 个 tool 消息添加了 `tool_call_id`
3. 孤立 tool 消息 (无匹配 assistant): 改回 `role=user`
   - 15551 个消息 (前一事件遗留的 context)

## 结果
- 0 orphan tool messages
- 所有 tool_calls ↔ tool 正确配对
- HF 已重新同步: `monokoco/affine-sft-data/memorygym.jsonl`

## 验证
预期 20000 条全部通过 ms-swift 验证。
