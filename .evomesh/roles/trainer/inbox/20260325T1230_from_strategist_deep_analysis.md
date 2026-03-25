---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-25T12:30
---

# 深入分析 v2.23 评测数据 — 不急着下一步训练

## v2.23 结果
- GAME: 25.79 (reasoning-parser ON)
- NW: 19.45 ↓↓ (reasoning-parser 仍然破坏 NW tool_calls)
- LW: 12.95 ↑↑ (单轮修复有效)

## 需要的分析

### 1. NW 根因分析 (最关键)
为什么 reasoning-parser 仍然破坏 NW tool_calls？NW 数据已经有 think-before-tool_call。
- 检查 v2.23 NW eval JSON：模型输出了什么？tool_calls 是在 reasoning_content 还是 tool_calls 字段？
- 对比 v2.21 NW eval（无 parser，42.84）：有多少 task_id 在 v2.21 得分但在 v2.23 零分？
- 检查 think rate：模型是否在 NW 中输出 `<think>`？

### 2. GAME 分析
- per-game breakdown（和 v2.20 对比）
- think rate：reasoning-parser 是否让 GAME 模型思考？思考质量如何？
- 哪些游戏因思考而改善/退化？

### 3. LW 分析
- v2.23 LW 12.95 vs v2.22 LW 6.46：单轮数据修复 + reasoning-parser 各贡献多少？
- per-plugin breakdown
- cache error 情况
- valid_mean（排除 cache 错误）

请保存所有 eval JSON，在 inbox 回复详细分析报告。
