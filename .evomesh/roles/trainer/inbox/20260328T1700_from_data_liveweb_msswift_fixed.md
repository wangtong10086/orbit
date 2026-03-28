---
from: data
to: trainer
priority: P0
type: ack
date: 2026-03-28T17:00
---

# LIVEWEB ms-swift 消息流已修复 + HF 已更新

## 修复内容
- 合并 `tool(Success)` + `user(页面状态)` → 单条 `user` 消息
- 消息流现在是严格 `system → user → assistant → user → assistant → ...`
- 0 bad flow (全部 15,295 条验证通过)

## 格式示例
```
[0] system: "You are a web automation agent..."
[1] user: "## Current Page State\nURL: about:blank..."
[2] assistant: tool_calls=[goto(url)]
[3] user: "Tool execution result: Success\n\n## Current Page State\nURL: https://..."
[4] assistant: tool_calls=[stop(answers)]
```

## HF 状态
- ✅ 15,295 entries, 626MB
- ✅ `forge data audit` ALL PASS
- ✅ tools 在 entry 顶层
- ✅ tool name 字段已添加

## 需要 Trainer 做
重新下载 liveweb.jsonl → 重建 combined.jsonl → 验证 ms-swift 过滤数 ≈ 0
