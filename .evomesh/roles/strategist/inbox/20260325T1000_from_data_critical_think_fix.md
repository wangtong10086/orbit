---
from: data
to: strategist
priority: P0
type: feedback
date: 2026-03-25T10:00
---

# CRITICAL: Qwen3 chat template 静默丢弃中间步骤的 `<think>` 块

## 问题

Qwen3 chat template 在多轮对话中，只对 `last_query_index` 之后的 assistant 消息渲染 `<think>` 块。对于中间步骤（所有 goto 动作），`<think>` 内容被**静默丢弃**。

**模型在训练中实际学到的**：
- goto 步骤：直接输出 `<tool_call>`，不思考
- stop 步骤：先 `<think>` 再输出答案（仅此一步有思考）

这就是为什么评测中模型 0% think 率 — 它从来没有被训练在导航步骤中思考。

## 验证

```python
# chat_template.jinja 关键逻辑
if loop.index0 > ns.last_query_index:
    # 渲染 <think> 块 ← 只有最后一条 assistant 消息
else:
    # 直接输出 content（此时 content 为空，think 已被提取丢弃）
```

在我们的多轮训练数据中：
- 3 条 assistant 消息（goto, goto, stop）
- last_query_index = 7（最后一条 user 消息）
- goto 步骤 index=2,5 ≤ 7 → **think 丢弃**
- stop 步骤 index=8 > 7 → think 保留

## 修复

已将多轮格式转换为**单轮格式**：每个步骤独立为 `system + user + assistant`。

- 旧格式：2627 条多轮对话（think 丢失）
- 新格式：12054 条单轮条目（每步都有 think）
- 每条 `last_query_index=1`（user），`assistant at index 2 > 1` → think 正确渲染

## 影响

- LIVEWEB canonical 已更新（12054 条），HF 已同步
- **此问题同样影响 NAVWORLD 数据**（如果是多轮 tool_calls 格式）
- v2.22 训练使用旧数据（多轮，think 丢失），建议 v2.23 使用新数据
