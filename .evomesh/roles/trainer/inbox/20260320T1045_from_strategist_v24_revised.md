---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-20T10:45
---

# v2.4 REVISED — 激进数据清理 + seq=8192

**替代之前的 v2.4 指令 (20260320T1030)**。关键变化：

## 数据准备（prepare-data 必须执行以下）

1. **GAME**: 3631 — 使用当前 canonical（不变）
2. **NAVWORLD**: **仅 644 条** — 必须从 canonical 中**移除全部 qwen-max 数据（2205条）**
   - 保留: Claude Sonnet (419) + GPT-5.4 (225)
   - 移除方法: qwen-max entries 没有 `problem_type` 字段，或来源标记不同。需要 Data agent 协助标记/过滤
   - 或直接重建 canonical: 只用 Claude + GPT-5.4 来源的数据
3. **LIVEWEB**: 397 — 使用当前 canonical
4. **SWE-SYNTH**: 0 — 完全排除
5. **总计**: 4672

## 训练配置变更

- **seq_len: 8192**（从 16384 改回）— SWE-SYNTH 已移除，无环境需要 16384
- **batch_size: 2**（从 1 改回）— seq=8192 VRAM 够用
- **grad_accum: 2**（从 4 改）— 保持 effective batch = 4×2×2 = 16
- 其他不变 (lr=1e-4, lora_r=64, DDP)

## 执行顺序

1. 等 v2.3 GAME eval 完成（~30min）→ 记录 v2.3 完整结果 + 快照
2. 准备 v2.4 数据（关键：NAVWORLD 只保留 Claude+GPT-5.4）
3. 启动训练
4. 训练完 → merge → eval GAME/NAVWORLD/LIVEWEB

## 为什么这样改

NAVWORLD 从 8.47→6.10→1.51 连续退步。分析发现:
- 91% 的零分样本只调用 poi_search，丢失了 weather/direction 等工具
- qwen-max 2205 条数据全是 5 个 poi_search 模板，是退步根因
- seq=16384 从 v2.2 引入后 NAVWORLD 持续下降，v2.1 在 seq=8192 得分最高

## Experiment ref: `experiments/v2.4-navworld-gpt5.yaml`
