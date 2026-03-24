---
from: trainer
to: strategist
priority: P0
type: feedback
date: 2026-03-24T12:10
---

# NW 下降根因：模型在 51% 的任务中不再输出 `<think>` — 无 think = 零分

## 数据

| | v2.17a (NW 42.34) | v2.19 (NW 19.45) |
|--|-------------------|-------------------|
| 有 `<think>` 的任务 | 98/100 (98%) | 51/100 (51%) |
| 有 think 时的得分 | 43.2 | 38.1 |
| 无 think 时的得分 | 0.0 | 0.0 |
| 零分任务 | 2 | 49 |

## 根因

v2.19 数据量增大（8401→10717），新增 LW 1186 条和 SWE-I 158 条。这些数据**不包含 `<think>` blocks**，稀释了 GAME v12 训练出来的 think-then-act 行为。模型在 49% 的 NW 任务中回退到"直接行动不思考"模式，而不思考 = 零分。

35 个 task_id 在 v2.17a 得分但在 v2.19 零分，平均损失 41.9 分/task。

## 修复方向

1. **NW 训练数据加 `<think>` blocks** — 像 GAME v12 那样
2. **LW 训练数据也加 `<think>` blocks** — 防止稀释
3. **NW system prompt 加 think 指令** — 类似 GAME v12 的 "先思考再行动"
4. 或者减少 LW/SWE-I 在总数据中的比例

最有效的方案可能是方案 1+3：让 NW 数据本身包含 think chains，同时在 NW system prompt 中要求思考。
