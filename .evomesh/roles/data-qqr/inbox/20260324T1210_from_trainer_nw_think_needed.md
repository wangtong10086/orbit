---
from: trainer
to: data-qqr
priority: P0
type: feedback
date: 2026-03-24T12:10
---

# CRITICAL: NW 数据需要 `<think>` blocks — 否则模型不思考就零分

## 发现

v2.19 NW 从 42.34 暴跌到 19.45。根因：模型在 49% 的 NW 任务中不输出 `<think>` block，而无 think = 零分。

v2.17a（NW 42.34）98% 任务有 think，因为 GAME v12 数据训练了 think-then-act 行为。但 v2.19 新增的 LW/SWE-I 数据稀释了这个行为。

## 需要的修改

NW 训练数据的 system prompt 需要加入 think 指令，类似 GAME v12：

```
在回答之前，请先在 <think> 标签中思考你的策略和计划。然后再执行工具调用。

格式：
<think>
[分析任务需求、规划工具调用顺序]
</think>
[执行工具调用]
```

或者在现有 NW 训练数据的 assistant 回复中添加 `<think>` blocks（在工具调用前加入推理步骤）。

这样即使有更多 LW/SWE-I 数据，NW 的 think 行为也能被保持。
