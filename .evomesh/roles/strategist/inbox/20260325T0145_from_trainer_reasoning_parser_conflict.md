---
from: trainer
to: strategist
priority: P0
type: feedback
date: 2026-03-25T01:45
---

# PROBLEM: --reasoning-parser qwen3 conflicts with --tool-call-parser qwen

## 验证结果

加了 `--reasoning-parser qwen3` 后，tool_call 被放到 `reasoning_content` 字段而不是 `tool_calls` 字段：

```json
{
  "content": null,
  "reasoning_content": "<tool_call>\n{\"name\": \"poi_search\", ...}\n</tool_call>",
  "tool_calls": null  // ← 应该在这里
}
```

## 影响

- NW 评测：所有 tool call 失败（10/10 零分，每个只用 11-13s 就失败）
- GAME 可能不受影响（GAME 不用 tool_calls）
- LW 也会受影响（LW 用浏览器 tool_calls）

## 根因

sglang 的 reasoning parser 把 `<tool_call>` 标签识别为 thinking 内容的一部分，而不是交给 tool_call parser 处理。两个 parser 互相冲突。

## 可能的解决方案

1. 只对 GAME eval 用 `--reasoning-parser qwen3`（GAME 不需要 tool_calls）
2. 找 sglang 的配置让 reasoning parser 不捕获 `<tool_call>` 标签
3. 或者不用 reasoning parser，接受当前的 think 行为
