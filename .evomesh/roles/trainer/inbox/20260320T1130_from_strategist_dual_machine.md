---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-20T11:30
---

# 双机并行 A/B 训练：seq=8192 vs seq=16384

用户提供了两台机器。用来做**并行对照实验**，一次确认 seq_len 是否是 NAVWORLD 退步根因。

## 实验设计

**相同数据，唯一变量 = seq_len**

| | 机器 A (v2.4a) | 机器 B (v2.4b) |
|---|---|---|
| **seq_len** | **8192** | **16384** |
| batch_size | 2 | 1 |
| grad_accum | 2 | 4 |
| effective batch | 16 | 16 |
| 数据 | 5234 (相同) | 5234 (相同) |
| lr | 1e-4 | 1e-4 |
| lora_r | 64 | 64 |
| 其他 | 全部相同 | 全部相同 |

## 两台都执行以下步骤

1. **准备数据** — `forge rental prepare-data` 用最新 canonical:
   - GAME: 3918（7游戏均衡, 含GPT-5.4蒸馏）
   - NAVWORLD: 919（零qwen-max, 纯Claude+GPT-5.4）
   - LIVEWEB: 397
   - **排除 SWE-SYNTH**
   - 总计: 5234
2. **启动训练** — 各自用对应的 seq_len 配置
3. **训练完成 → merge LoRA → sglang → eval**
   - 评测 3 环境: GAME 100s + NAVWORLD 100s + LIVEWEB 100s
   - `--tool-call-parser qwen25`

## 预期结果

| 场景 | v2.4a (8192) | v2.4b (16384) | 结论 |
|------|-------------|-------------|------|
| seq 是根因 | NAVWORLD ≥8 | NAVWORLD ~1-3 | 确认 seq=8192 更好，后续固定 8192 |
| seq 不是根因 | NAVWORLD ~1-3 | NAVWORLD ~1-3 | 问题在别处，需要查其他变量 |
| 都恢复 | NAVWORLD ≥8 | NAVWORLD ≥8 | 是数据清理（qwen-max移除）起了作用 |

## Experiment ref
- v2.4a: `experiments/v2.4-navworld-gpt5.yaml` (seq=8192)
- v2.4b: 同一实验的对照组 (seq=16384)
