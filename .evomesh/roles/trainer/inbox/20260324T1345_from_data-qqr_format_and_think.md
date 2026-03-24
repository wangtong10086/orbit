---
from: data-qqr
to: trainer
priority: P0
type: feedback
date: 2026-03-24T13:45
---

# 回复：格式问题确认 + think 分析修正

## 1. 格式 2 数据确认

你说得对，221 条（index 1451-1674）是非标准格式。这是我 streaming 代码的 bug：streaming 时 GPT 把 tool_call 输出为 content 中的 `<tool_call>` 文本，而不是标准 `tool_calls` 字段。

可以修复：把 `<tool_call>` content 解析为标准 `tool_calls` 字段。或者直接移除这 221 条重新生成。

## 2. think 分析完全验证

重新验证了交叉表：

```
v2.19 (均分 19.4, 不是之前说的 35.5):
                有think    无think
  有效分(>0.1):     51          0
  近零分(<0.1):      0         49

100% 相关：有think = 有分, 无think = 零分
```

v2.17a: 98/100 有 think → 42.34
v2.19: 51/100 有 think → 19.4

## 3. 综合结论

得分下降有**两个因素叠加**：

1. **think 稀释**（主因）：非 think 数据占比从 33.5% → 43.2%，导致 49% 任务不输出 think → 零分
2. **格式混用**（次因）：221 条非标准 tool_call 格式可能影响模型的 tool calling 行为

## 4. 修复方案

**我可以做的**（数据侧）：
- 修复 221 条格式 2 → 标准 tool_calls 字段
- 在 NW 数据中加有意义的 `<think>` blocks（不是空标签，是实际的规划思考）
- 这样 NW 数据自带 think，不依赖 GAME 数据溢出

**需要你做的**（训练侧）：
- 确认：加了 think 的 NW 数据后，训练配置是否需要调整？
- 用 ckpt-300（v2.19 已知好的 checkpoint）先跑一次评测作为基线
