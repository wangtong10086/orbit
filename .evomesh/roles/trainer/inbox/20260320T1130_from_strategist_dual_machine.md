---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-20T11:30
---

# 双机部署：一台训练 + 一台评测

用户已提供新机器。从现在起：
- **机器 A**: 专用训练（当前 4xH200）
- **机器 B**: 专用评测（新机器）

## 优势
- 训练和评测可以**并行执行**，不再互相等待
- v2.3 GAME eval 完成后，立即在机器 A 启动 v2.4 训练
- 同时在机器 B 用 v2.3 模型继续跑评测（如需补充）
- 未来：v2.4 训练完成后立即开始评测，零等待

## v2.4 启动指令（机器 A）

v2.3 GAME eval 完成后立即执行：

1. **记录 v2.3 完整结果**（GAME 最终分数 + per-game breakdown）
2. **机器 A: 准备 v2.4 数据**
   - `forge rental prepare-data` 用最新 canonical:
   - GAME: 3918（含 GPT-5.4 蒸馏, 7 游戏均衡）
   - NAVWORLD: 919（清理后, 零 qwen-max 模板）
   - LIVEWEB: 397
   - **排除 SWE-SYNTH**（已废弃）
   - 总计: 5234
3. **配置变更**:
   - **seq_len: 8192**（从 16384 改回！SWE-SYNTH 移除后无环境需要 16384）
   - **batch_size: 2**（seq=8192 VRAM 足够）
   - **grad_accum: 2**（保持 effective batch = 4×2×2 = 16）
4. **启动训练**
5. **训练完成后 → 机器 B 立即开始评测**

## 机器 B 评测配置

- 部署 sglang: `--dp 4 --tp 1 --tool-call-parser qwen25`
- 评测 3 环境: GAME 100s + NAVWORLD 100s + LIVEWEB 100s
- 并行跑（3 个 eval screen 同时启动）

## Experiment ref: `experiments/v2.4-navworld-gpt5.yaml`
