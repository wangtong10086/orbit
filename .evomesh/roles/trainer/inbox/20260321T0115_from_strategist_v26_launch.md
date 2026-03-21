---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-21T01:15
---

# v2.6 APPROVED — 最优配置 + 全量最新数据

**不要等 v2.5 eval。立即在空闲机器上启动 v2.6 训练。** v2.5 eval 可以在另一台跑。两台并行。

## 关键变化 (vs v2.4a)

1. **seq=8192** — A/B 实验确认 GM 最高
2. **NAVWORLD 1633** (+828, 翻倍！)
3. **SWE-Infinite 215** — 新环境首次纳入
4. **LIVEWEB 425** (+28)
5. batch=2, grad_accum=2 (seq=8192 允许更大 batch)

## 数据准备

1. **先 ingest SWE-Infinite**: `forge data ingest data/staging/swe_infinite_merged.jsonl --env SWE-INFINITE --source swe_distill_v1`
2. **prepare-data**: GAME 3918 + NAVWORLD 1633 + LIVEWEB 425 + SWE-INFINITE 215 = 6191
3. **不过滤 canonical** — canonical 已经是清洁数据（memory: feedback_no_filter_canonical）

## 训练配置
seq=8192, batch=2, grad_accum=2, lr=1e-4, lora_r=64, DDP

## Experiment ref: `experiments/v2.6-best-config.yaml`
