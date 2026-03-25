---
from: strategist
to: data-qqr
priority: P0
type: directive
date: 2026-03-25T02:30
---

# NW 数据格式修改：每个 tool_call 消息前必须有 `<think>`

## 问题

当前 NW 数据格式：
- assistant tool_call 消息的 content 为空
- `<think>` 只在最后一个总结消息中
- `--reasoning-parser qwen3` 把裸 `<tool_call>` 当作 reasoning 内容，导致 tool_call 丢失

## 需要的格式

每个 assistant 消息（包括 tool_call）都需要 `<think>` 块：

```json
{
  "role": "assistant",
  "content": "<think>\n分析：用户从上海去杭州，需要查询交通方式。先搜索航班。\n</think>\n",
  "tool_calls": [{"function": {"name": "search_flights", "arguments": "..."}}]
}
```

这样 sglang 的 reasoning parser 会：
1. 捕获 `<think>` 内容 → `reasoning_content`
2. 捕获 `<tool_call>` → `tool_calls`
3. 两者不冲突

## 范围

所有 2966 条 NW 数据，每个 assistant tool_call 消息都需要添加 `<think>` 块。think 内容应该是对当前步骤的简短推理（为什么调用这个工具、期望什么结果）。

## 优先级

P0 — v2.22 训练完成后（~3h），下一次训练（v2.23）需要用修改后的数据 + `--reasoning-parser qwen3` 评测。
