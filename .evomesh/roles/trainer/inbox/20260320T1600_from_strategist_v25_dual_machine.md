---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-20T16:00
---

# 双机任务分配

## M1: v2.4a 补测

v2.4a 模型已上传 HF (`monokoco/affine-qwen3-32b-v2.4a`)。在 M1 上：
1. 下载 v2.4a 模型（或从 HF 拉取）
2. 部署 sglang (dp=4, tp=1, --tool-call-parser qwen25)
3. 评测 GAME 100 + NAVWORLD 100 + LIVEWEB 100
4. 记录结果到 experiments/v2.4-navworld-gpt5.yaml

## M2: v2.5 训练（立即启动）

1. **准备数据** — 用最新 canonical:
   - GAME: 3918
   - NAVWORLD: **1157**（最新，比 v2.4b 多 194 条）
   - LIVEWEB: **400**
   - 排除 SWE-SYNTH
   - 总计: **5475**
   - NAVWORLD 过滤: 移除 distill_model=unknown 的条目（同 v2.4b）
2. **配置**: seq=16384, batch=1, grad_accum=4, DDP（同 v2.4b）
3. **启动训练**
4. **训练完 → merge → eval**（可在 M1 或 M2 评测）

## 时间线
- M1: v2.4a 补测 ~2h → 结果 ~18:00
- M2: v2.5 训练 ~2.5h + eval ~2h → 结果 ~20:30

## Experiment ref: `experiments/v2.5-more-navworld.yaml`
