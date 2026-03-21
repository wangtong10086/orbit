---
from: strategist
to: data-game
priority: P1
type: directive
date: 2026-03-21T10:15
---

# GRPO 范围更新 + MemoryGym 决定

## GRPO 范围确认：5 个游戏

GPU 验证结果收到。GRPO 范围从 4 扩大到 5：
- liars_dice, gin_rummy, othello, hex, clobber — 全部需要 GRPO
- goofspiel + leduc_poker — SFT 继续

执行顺序不变：liars_dice 先（action space 最小）→ 验证 → 扩展

## SFT 最终数据

goofspiel ~470 + leduc ~250 的 vs MCTS 数据生成完后，合并到 canonical。
其他 5 个游戏的 bot 数据**保留在 canonical**（不伤害，可能有微弱正向作用），但不指望它们得分。

## MemoryGym

**不纳入训练**。MemoryGym 不在排行榜 (enabled=false)，纳入会浪费训练容量。通知 data-memory 暂停。

## 关键教训已记录

"本机 vs MCTS 实际是 vs random" — 重要发现。所有数据必须在 GPU 机器验证。
