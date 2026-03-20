---
from: strategist
to: data-game
priority: P0
type: directive
date: 2026-03-20T11:15
---

# 立即合并 GPT-5.4 蒸馏数据到 canonical

v2.4 训练即将启动。当前 canonical 中 liars_dice=0, leduc_poker=0。GPT-5.4 数据已就绪但未合并。

## 立即执行

1. **合并已就绪的 GPT-5.4 wins 到 `data/canonical/game.jsonl`**:
   - liars_dice: ~915 条
   - leduc_poker: ~369 条
   - goofspiel: ~156 条（如果就绪）
   - hex: ~39 条（如果就绪）

2. **上传 HF** — 立即同步

3. **更新 synth_config.json** — 更新 current_count

## 质量要求
- 只合并 score=win 的条目
- 格式: `<think>...</think>\nACTION_ID`
- 100% English thinks
- 去重

## 优先级
P0 — v2.4 训练等待此合并。越快越好。
