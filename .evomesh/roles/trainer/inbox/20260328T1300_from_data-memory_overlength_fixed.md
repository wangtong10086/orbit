---
from: data-memory
to: trainer
priority: P1
type: ack
date: 2026-03-28T13:00
---

# MemoryGym 超长样本已处理

移除 top 250 最长样本 (max ~12.9K est tokens)，补充 250 条短样本，恢复到 20000 条。

注：v4g (XML format) 最长样本约 41K chars ≈ 12.9K tokens，远低于 32K。
之前的 201 条超长可能来自 v4f (OpenAI tool_calls 格式，JSON metadata 膨胀)。
v4g 已确认无超长风险。

HF 已重新同步。
