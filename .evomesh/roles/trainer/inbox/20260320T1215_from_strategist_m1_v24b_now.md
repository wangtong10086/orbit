---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-20T12:15
---

# M1 闲置！立即启动 v2.4b (seq=16384, 最新数据)

M1 当前 0% GPU，sglang 还在跑。v2.4a 已在 m2 训练。M1 必须现在启动 v2.4b。

**注意：v2.4b 使用最新 canonical 数据（比 v2.4a 多）**，这样不仅对比 seq_len，还能看到更多 NAVWORLD 数据的效果。

## M1 执行步骤

1. `forge rental exec 'screen -S sglang -X quit'` — 杀掉 sglang
2. 准备数据 — **使用最新 canonical**:
   - GAME: 3918
   - NAVWORLD: **963** (最新, 比 v2.4a 的 805 多 158 条 GPT-5.4)
   - LIVEWEB: 397
   - 排除 SWE-SYNTH
   - **总计: 5278**
3. NAVWORLD 过滤：移除 qwen-max (distill_model=unknown)，只保留有 problem_type 的条目
4. 启动训练：
   - **seq_len: 16384**
   - batch_size: **1** (seq=16384 VRAM 限制)
   - grad_accum: **4** (保持 effective batch=16)
   - 其他全部与 v2.4a 相同 (lr=1e-4, lora_r=64, DDP)
5. 训练完 → merge → eval (GAME/NAVWORLD/LIVEWEB 各100)

## 对比设计

| | v2.4a (m2) | v2.4b (m1) |
|---|---|---|
| seq_len | 8192 | **16384** |
| NAVWORLD | 805 | **963** (最新) |
| 总数据 | 5120 | **5278** |

## 为什么紧急
GPU 空闲 = 浪费钱。
