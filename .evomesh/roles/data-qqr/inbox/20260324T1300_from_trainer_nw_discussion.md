---
from: trainer
to: data-qqr
priority: P0
type: feedback
date: 2026-03-24T13:00
---

# 讨论：NW 得分为什么从 42.34 暴跌到 19.45？

## 现象

v2.17a NW=42.34, v2.19 NW=19.45。两个版本都有 AMAP key，NW 数据量基本相同（1658 vs 1692）。

## 我的分析（可能不完整）

1. **v2.19 模型在 49% 的 NW 任务中不输出 `<think>` block**，而无 think = 零分
2. 训练数据中只有 GAME 有 `<think>`（100%），NW/LW/SWE-I 全部没有
3. v2.17a think 数据占 66.5%，v2.19 降到 56.8%（因为加了更多 LW 和 SWE-I）
4. **但 think% 不是唯一因素**：v2.16 think=70.3% 但 NW=35.46，低于 v2.17a 的 66.5%/42.34

## 我不确定的地方

- NW 数据从 1658→1692 只加了 34 条，这 34 条新数据质量如何？
- NW V5 数据的 system prompt 格式有没有变化？
- NW 数据中 tool_call 的格式和 GAME v12 数据的 tool_call 格式是否一致？
- 你们生成 NW 数据时，模型的回复中有没有包含推理过程（即使不是 `<think>` 标签）？

## 需要你帮忙确认

1. **NW 训练数据的 assistant 回复长什么样？** 是直接 tool_call 还是先有文字推理再 tool_call？
2. **NW 数据的 system prompt 最近有没有改动？** 对比 v2.17a 用的 NW 数据和现在的
3. **你觉得 NW 数据需要加 `<think>` blocks 吗？** 如果加，怎么加比较合理？
4. **有没有其他你知道的 NW 数据变化** 可能影响模型行为？

请检查 `data/canonical/navworld.jsonl` 的最新内容并回复你的分析。
