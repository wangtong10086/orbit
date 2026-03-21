---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-21T08:00
---

# M2 立即启动 v2.8 (epochs=2, lr=7e-5)

## 核心发现：之前所有训练都不够！

v2.1 (loss 0.156, NW 8.47) 跑了 ~430 步 / 56.4M tokens。
v2.6/v2.7 只跑了 268 步 / 35.1M tokens — 少了 38%。这就是 loss 降不下去的原因。

## M2 配置

1. 数据 — 最新 canonical（不过滤）: GAME **4405** + NW 1633 + LW 438 + SWE-I 215 = **6691**
2. **关键参数变化**:
   - **epochs: 2** ← 翻倍训练量（~536 步, ~70M tokens）
   - **lr: 7e-5** ← 2 epoch 需要更低 lr 防止过拟合
   - seq=8192, batch=2, grad_accum=2, DDP
3. 启动训练
4. **eval 必须 `source /root/.env`** — CHUTES_API_KEY 必须生效

## 目标
- loss < 0.20（匹配 v2.1 水平）
- NAVWORLD ≥10
- GAME ≥26

## Experiment ref: `experiments/v2.8-lr-tuned.yaml`
