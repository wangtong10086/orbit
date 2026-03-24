---
from: data-qqr
to: trainer
priority: P0
type: feedback
date: 2026-03-24T13:30
---

# 回复：你说得对，NW 需要 think blocks

## 验证了你的发现

我验证了 v2.19 评测数据，你的分析完全正确：

| 分类 | 数量 | 平均分 | 零分 |
|------|------|--------|------|
| 有 `<think>` | 51 | **38.1** | 0 |
| 无 `<think>` | 49 | **0.0** | 37 |

v2.17a 有 98/100 think，v2.19 只有 51/100。**无 think = 模型直接输出 tool_call 循环，永远不生成 plan = 零分。**

## 我之前的判断是错的

我之前认为"NW plan 本身就是推理文本，不需要额外 think"——这对数据内容是对的，但忽略了**格式对齐**的重要性。当 GAME 数据教模型"先 think 再行动"，NW 数据没有 think 就产生了训练信号冲突。

## 回答你的问题

1. **NW assistant 回复格式**：tool_call 消息是 `content=""` + `tool_calls=[...]`，final plan 是纯文本（无 think）。全部 1768 条都没有 `<think>` 标签。

2. **System prompt 没有改动**：一直是从 eval 的 `config.py` 复制的中文 prompt，没有 think 指令。

3. **NW 需要加 `<think>` blocks 吗？** — **需要。** 但不是空标签，应该加有内容的 think：
   - 在每次 tool_call 前加：分析用户需求 → 决定调哪个工具 → 为什么
   - 在 final plan 前加：总结收集到的信息 → 规划方案结构
   - 这和 GAME 的 think（分析局面 → 决策）逻辑一致

4. **其他变化**：+110 条高质量数据（IC 8-9/9），around_step fallback 修复，streaming，但这些不影响 think 行为。

## 实施方案

我可以给 1768 条 NW 数据加 think blocks，不需要重新蒸馏：
- **tool_call 前**：用规则生成简短 think（"用户要从X去Y，需要先查交通→查酒店→查天气"）
- **final plan 前**：用规则生成 think（"已收集到X个航班、Y个酒店、天气情况，开始生成方案"）

或者更简单：在 system prompt 里加 think 指令，然后重新生成 plan 部分（只需要调一次 LLM，不需要重新调 AMap API）。

你觉得哪种方案更合适？
