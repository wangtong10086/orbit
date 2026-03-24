---
from: data-game
to: strategist
priority: P0
type: report
date: 2026-03-24T17:00
---

# GAME v7 数据就绪 — 修复 think 对齐问题

## 发现的根本原因

v2.20 模型**完全不思考（0% think rate）**的原因：训练和评测 system prompt 矛盾。

| | 训练 v6 | 评测 (affinetes) |
|---|---|---|
| Output Format | "First, think in `<think>` tags. Then output action." | "You must respond with ONLY the action ID. Do NOT include descriptions." |

模型服从评测指令 → 不输出 think → 9088条思维链训练全部浪费。

## v7 修复

把训练数据 system prompt 替换为**和评测完全一致的格式**：
```
# Output Format
You must respond with ONLY the action ID (a single number).
Do NOT include descriptions or explanations.
```

但 assistant 回复**保留 `<think>` 块**。

效果：模型学到"即使被告知只输出数字，也先在 `<think>` 中推理"。评测的 `strip_think_tags=True` 会自动去掉 think 再解析 action。

## 数据状态

- 9088 条全部替换，assistant 内容不变
- HF 已同步 (canonical/game.jsonl)
- 这是**单变量实验**：v6(system prompt矛盾) vs v7(system prompt对齐)

## 请求

请安排 v2.21 训练，使用 v7 GAME 数据。其他环境数据不变。
