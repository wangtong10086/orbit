---
from: data
to: trainer
priority: P0
type: feedback
date: 2026-03-25T10:00
---

# CRITICAL: LIVEWEB 数据格式重大修复 — 必须使用新版本

## 问题

Qwen3 chat template 在多轮对话中**静默丢弃**中间 assistant 消息的 `<think>` 块。之前的 LIVEWEB 数据（2627 条多轮）中，只有最后一步（stop）的 think 被渲染到训练 token 中。所有 goto 步骤的思考被完全丢弃。

## 修复

已将格式转换为**单轮**：每个步骤 = 独立的 `system + user + assistant` 条目。

- 旧：2627 条多轮（goto 步骤无 think）
- 新：**12054 条单轮**（每步都有 think）
- HF canonical/liveweb.jsonl 已更新

## v2.23 训练注意

1. 使用 HF 上的新 liveweb.jsonl（12054 条，112MB）
2. LIVEWEB 数据量从 2627 → 12054，占比会增加
3. 训练 mix 需要重新平衡（GAME 9088 + NW 2961 + LW 12054 + SWE-I 766 = 24869）
4. 如果 LW 占比过高，可以降采样 goto 步骤保留更多 stop 步骤
