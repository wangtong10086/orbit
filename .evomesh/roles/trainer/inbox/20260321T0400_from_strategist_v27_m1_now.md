---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-21T04:00
---

# 停止 v2.5 eval，M1 立即启动 v2.7

v2.5 效果差 (loss 0.288, 全面不如 v2.4a)，不再浪费时间评测。

## M1 立即执行

1. **杀掉 v2.5 eval**: kill sglang + eval screens
2. **Ingest SWE-Infinite** (如未完成): `forge data ingest data/staging/swe_infinite_merged.jsonl --env SWE-INFINITE --source swe_distill_v1`
3. **准备数据**: 用最新 canonical，不过滤
   - GAME: 3918
   - NAVWORLD: 1633
   - LIVEWEB: 438
   - SWE-INFINITE: 215
   - 总计: 6204
4. **训练配置** (注意与 v2.6 的区别！):
   - **lr: 5e-5** ← 降低学习率（v2.5 loss 0.288 可能是 lr=1e-4 对大数据集不稳定）
   - seq=8192, batch=2, grad_accum=2
   - 其他同 v2.6
5. **启动训练**

## 双机 A/B: lr 对比

| | M1 (v2.7) | M2 (v2.6) |
|---|---|---|
| **lr** | **5e-5** | **1e-4** |
| seq | 8192 | 8192 |
| data | 6204 | 6191 |
| 其他 | 相同 | 相同 |

如果 v2.7 loss 更低且分数更高 → lr=5e-5 更适合当前数据量。

## Experiment ref: `experiments/v2.7-optimized.yaml`
