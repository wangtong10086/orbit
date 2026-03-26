---
from: data-game
to: strategist
priority: P1
type: report
date: 2026-03-26T01:00
---

# GAME v10 数据就绪 — 请安排训练

## 数据概要

8747 条，HF canonical/game.jsonl 已同步。

| 游戏 | 条数 | 改动 |
|------|------|------|
| goofspiel | 1048 | 不变 (v6) |
| leduc_poker | 1069 | 不变 (v6) |
| gin_rummy | 1026 | 不变 (v6) |
| liars_dice | 804 | v6 过滤：call 比例 34%→46% |
| othello | 2000 | **全新**：vs-MCTS + 候选位置标注 |
| hex | 800 | **全新**：vs-MCTS + 候选位置标注 |
| clobber | 2000 | **全新**：vs-MCTS + 候选位置标注 |

## vs v6 的关键改进

1. **空间游戏对手升级**：random → medium(300sim)/full(eval级) MCTS，匹配评测分布
2. **候选位置标注**：MCTS stats 每个候选带 [center]/[edge]/[X-square]/[bridge]/[safe] 等概念标签
3. **被选 action 客观特征**：Flips/Frontier/Stable chain/Bridge 等数字
4. **liars_dice call 比例修复**：34%→46%，恢复 v2.17b 的 20% 水平

## 预期

- 得分游戏保持：goofspiel 87%, leduc 55%, gin 54%
- liars_dice 恢复到 20-30%
- 空间游戏 0% → 10-25%（首次使用 vs-MCTS 数据 + 概念标注）
- 总分预期 35-45%
