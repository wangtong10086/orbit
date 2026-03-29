---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-29T01:00
---

# v2.28 训练停在 step 800 — 用新数据 155k 重启

## 状况
训练在 step 800/2847 停止（rank 4 exitcode 1）。Loss 0.41, 28% 完成。

## 新数据已上传
`/data/datasets/combined.jsonl` — **155109 条** (之前 91236)

| Env | 条数 |
|-----|------|
| GAME | 103592 |
| MemoryGym | 20000 |
| LW | 19776 |
| NW | 10006 |
| SWE-I | 1735 |

## 操作
用新数据从头重启训练。配置不变。
