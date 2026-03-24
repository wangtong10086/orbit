# Data-Game TODO

## v6 MCTS Stats Data — COMPLETE ✅

**Canonical: 9088 entries, 0 errors, HF synced.**
**All data generated with final verified code. No filtering needed.**

| Game | Count | Bot | Think Format |
|------|-------|-----|-------------|
| goofspiel | 1048 | Rule v4 | Rule think (hand/prize/bid) |
| leduc_poker | 1069 | Rule v4 | Rule think (pot odds/range) |
| liars_dice | 1829 | MCTS 10000sim | MCTS stats T1 + Rule fallback T2+ |
| gin_rummy | 1026 | MCTS 2000sim | MCTS stats (draw/discard/knock) |
| othello | 1358 | MCTS 3000sim | MCTS stats + corner/edge context |
| hex | 1211 | MCTS 3000sim | MCTS stats + bridge context |
| clobber | 1547 | MCTS 5000sim | MCTS stats + safe capture context |

## Think Chain Architecture
- MCTS search → extract child stats (visits + win rates)
- If visits > 1: "Evaluated N options: a1 (78%), d3 (42%)... Choosing a1."
- If visits ≤ 1: fallback to game-specific rule think
- Lookahead: opponent response → our counter (from search tree)
- System prompt: v12 (think in `<think>` tags)

## v2.20 Eval 接近完成 (85/100)

| 游戏 | v2.17b | v2.20 | N | 变化 |
|------|--------|-------|---|------|
| goofspiel | 86.7% | 84.6% | 13 | 采样波动 |
| leduc_poker | 52.5% | 55.8% | 13 | 持平 |
| gin_rummy | 45.6% | **52.8%** | 13 | **+7% MCTS有效** |
| liars_dice | 20.0% | **0.0%** | 12 | **回退!** |
| hex/othello/clobber | 0% | 0% | 34 | SFT天花板 |

**总均分 29.6%** ≈ v2.17b 29.7%

### 根因分析
- liars_dice: 之前赢的 2 个 task_id 在 v2.20 全输。MCTS think(avg 303 chars)让模型从"不思考但偶尔赢"变成"思考但全输"
- 空间游戏: 4x 数据无效，SFT 天花板铁板钉钉

### 下一步
- [ ] 拉取完整 JSON 确认 liars_dice 模型输出（think 内容 + action 有效性）
- [ ] 向 Strategist 发最终报告 + GRPO 提案
- [ ] 考虑 liars_dice 数据优化：减少 MCTS think 比例，保留 Rule think
