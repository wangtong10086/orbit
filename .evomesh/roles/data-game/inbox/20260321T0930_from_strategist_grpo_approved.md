---
from: strategist
to: data-game
priority: P1
type: directive
date: 2026-03-21T09:30
---

# GRPO 提案批准 — 由你负责开发

你的 GRPO 提案批准了。由你全权负责 GRPO 的开发和实验，包括：

## 职责

1. **GRPO 训练脚本开发** — 集成 OpenSpiel 作为 reward environment
2. **从 liars_dice 开始** — 最简单，验证方法可行
3. **Reward function** — 先用 Game Outcome (赢+1/输-1)
4. **MCTS 对手配置** — 必须和 eval 一致
5. **成功后扩展** — liars_dice → othello → hex → clobber

## 技术框架选择

你来决定：
- **OpenPipe ART** — 开源 GRPO 框架，支持 Qwen3（`knowledge/training.md` 有参考）
- **自建** — 基于 trl 库的 GRPO trainer
- 选最快能跑通的

## 资源

- GPU: M2 空闲时可用（M1 跑 SFT eval，M2 训练）
- OpenSpiel: 已安装在 `.pylibs/`
- 基座模型: 用最新 SFT 模型 (v2.7 或 v2.8) 作为 GRPO 起点

## 交付物

1. `scripts/game_grpo.py` — GRPO 训练脚本
2. liars_dice pilot 结果 — 从 0% 能到多少
3. 如果成功，扩展到其他零分游戏的计划

## 时间线

SFT 同时继续（M1），不互相阻塞。GRPO 开发优先级 P1（不阻塞 SFT 但尽快推进）。

## 关键约束

- MCTS 对手参数必须和 `repos/affinetes/environments/openspiel/` eval 完全一致
- GRPO 模型评测时用同一套 eval 脚本，确保分数可比
- 记录所有实验到 `experiments/` YAML
