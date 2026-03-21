---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-21T08:00
---

# M2 立即启动 v2.8 (lr=7e-5)

M1 继续跑 v2.7 eval。M2 空闲，立即训练。

## M2 执行

1. 准备数据 — 用最新 canonical（不过滤）:
   - GAME: 3918
   - NAVWORLD: 1633
   - LIVEWEB: 438
   - SWE-INFINITE: 215 (从 staging ingest 如未完成)
   - 总计: 6204
2. 配置: **lr=7e-5**, seq=8192, batch=2, grad_accum=2
3. 启动训练
4. **eval 时必须 `source /root/.env`** 确保 CHUTES_API_KEY 生效

## 为什么 lr=7e-5
- v2.6 lr=1e-4: GAME 26.66 最佳, loss 0.301 (高)
- v2.7 lr=5e-5: loss 0.22 (好), LIVEWEB 9.08 (差)
- 7e-5 折中：期望 loss ~0.24 + GAME ≥26 + 稳定 LIVEWEB

## Experiment ref: `experiments/v2.8-lr-tuned.yaml`
