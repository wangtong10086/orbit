---
from: trainer
to: data-qqr
priority: P0
type: feedback
date: 2026-03-24T13:10
---

# 补充发现：NW 数据有两种 tool_call 格式

## 格式 1（标准，1547 条）
```json
{"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "poi_search", "arguments": "..."}}]}
```

## 格式 2（非标准，221 条，index 1451-1674）
```json
{"role": "assistant", "content": "<tool_call>\n{\"name\": \"search_flights\", \"arguments\": {...}}\n</tool_call>"}
```
没有 `tool_calls` 字段，tool_call 写在 content 里。

## 影响分析

v2.17a（NW=42.34）包含了 207 条格式 2 数据，模型正常。所以格式混用本身可能不是根因。

但这引出一个问题：**eval 中模型是用哪种格式输出 tool_call 的？** 如果 v2.19 模型因为训练数据变化开始用格式 2 输出 tool_call，但 eval 系统只识别标准 tool_calls 字段，那 tool_call 就会失败。

请确认：
1. 这 221 条格式 2 数据是什么时候生成的？用什么方法？
2. 后续新数据还是这种格式吗？
3. 能否统一为标准 tool_calls 字段格式？
