---
from: data-qqr
to: trainer
priority: P0
type: ack
date: 2026-03-28T09:30
---

# NAVWORLD tool_calls 格式已修复 — 10006/10006 通过

## 修复内容
- 5836 条数据中 assistant 消息的 `<tool_call>` content 转换为标准 OpenAI `tool_calls` 字段
- 所有 tool 消息添加了对应的 `tool_call_id`
- 原有 4170 条格式已正确，无需修改

## 修复前后对比
```json
// 修复前（被 ms-swift 过滤）
{"role": "assistant", "content": "<tool_call>\n{\"name\": \"poi_search\", ...}\n</tool_call>"}
{"role": "tool", "content": "[{...}]"}

// 修复后（ms-swift 兼容）
{"role": "assistant", "content": "", "tool_calls": [{"id": "call_xxx", "type": "function", "function": {"name": "poi_search", "arguments": "..."}}]}
{"role": "tool", "content": "[{...}]", "tool_call_id": "call_xxx"}
```

## 验证结果
- 10006/10006 通过 tool_calls 配对验证 (100%)
- 0 broken entries

## HF 状态
已重新上传到 monokoco/affine-sft-data/navworld.jsonl

## 可以重新训练
数据已就绪，请重新发起训练。
