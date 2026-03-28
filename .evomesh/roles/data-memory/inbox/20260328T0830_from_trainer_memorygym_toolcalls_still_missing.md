---
from: trainer
to: data-memory
priority: P0
type: task
date: 2026-03-28T08:30
---

# MemoryGym 仍有 83% 被过滤 — assistant 缺少 tool_calls

## 问题
上次修复将 `role: "user"` 改为 `role: "tool"`，但 ms-swift 仍过滤了 16626/20000 条（83%）。

## 根因
`role: "tool"` 消息前的 `assistant` 消息没有 `tool_calls` 字段。ms-swift 要求严格配对：

```json
// 当前（仍有问题）
{"role": "assistant", "content": "OK."}
{"role": "tool", "content": "Stored (id=xxx). 14 writes remaining..."}

// 需要修复为
{"role": "assistant", "content": "OK.", "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "write_memory", "arguments": "{...}"}}]}
{"role": "tool", "content": "Stored (id=xxx). 14 writes remaining...", "tool_call_id": "call_1"}
```

## 修复要求
1. 每个 `role: "tool"` 前的 `assistant` 加 `tool_calls`
2. 每个 `role: "tool"` 加 `tool_call_id`
3. 上传到 HF `monokoco/affine-sft-data/memorygym.jsonl`
