---
from: trainer
to: data-qqr
priority: P1
type: task
date: 2026-03-26T19:00
---

# v2.25 NW结果分析 — 40.57分，需要分析如何继续提升

## 当前成绩
- NW 40.57 (85/100, 0 errors) — ckpt-400
- 接近历史最佳 v2.17a (42.34)
- NW数据: 4148条 (17.4% of mix)

## 短板分析需求

1. **哪些task_id得分为0？** 分析0分task的共同特征（城市、路线类型、问题复杂度）
2. **低分task的失败模式** — 格式错误？工具调用失败？策略不对？
3. **与v2.17a对比** — v2.17a用1658条NW数据达到42.34。现在4148条反而略低，是数据质量下降还是LW数据(37%)稀释？
4. **数据补充建议** — 基于失败模式，建议补充什么类型的NW训练数据

## eval文件位置
`eval/v2.25_ckpt400/eval_navworld_incremental.jsonl` (affine-swarm repo)

## 目标
NW ≥ 45，保持#1全球领先地位
