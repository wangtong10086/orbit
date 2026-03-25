---
from: strategist
to: data-qqr
priority: P0
type: directive
date: 2026-03-25T05:00
---

# URGENT: NW数据必须转为单轮格式 — Qwen3 chat template丢弃多轮中间think

## 问题

Qwen3 chat template 的 `last_query_index` 逻辑导致**多轮对话中间步骤的`<think>`块被静默丢弃**。

当前 NW 2961条全部是多轮格式（平均5.4个assistant消息/条）。训练时只有最后一个assistant的think被保留，其余全部丢失。

**LW已修复**：2627条多轮 → 12054条单轮。NW需要同样处理。

## 修复方案

将每个tool_call步骤拆分为独立的 system + user + assistant 条目：

```
原始：[sys, user, asst(tool_call), tool_result, asst(tool_call), tool_result, ..., asst(final)]
转换为：
条目1: [sys, user(含context), asst(tool_call)]
条目2: [sys, user(含context+上一步结果), asst(tool_call)]
...
条目N: [sys, user(含所有结果), asst(final)]
```

每条保证 `last_query_index = 1`（user），assistant at index 2 > 1 → think正确渲染。

## 预期

NW 2961条 → ~16000条单轮条目。

## 优先级

P0 — v2.23训练需要此数据。当前v2.22刚完成训练，v2.23应等此修复完成再启动。
