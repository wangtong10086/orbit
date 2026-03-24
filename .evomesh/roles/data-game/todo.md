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

## v2.20 Eval In Progress (69/100)

### 实时结果 (task_id 映射到 v2.17a 游戏分配)

| 游戏 | v2.17b | v2.20 | 样本 | 变化 |
|------|--------|-------|------|------|
| goofspiel | 86.7% | 83.3% | 12 | 采样波动 |
| leduc_poker | 52.5% | 54.1% | 10 | 持平 |
| gin_rummy | 45.6% | 53.5% | 11 | **+8% MCTS有效** |
| liars_dice | 20.0% | 0.0% | 10 | **回退!待分析** |
| hex | 0% | 0% | 7 | SFT天花板 |
| othello | 0% | 0% | 9 | SFT天花板 |
| clobber | 0% | 0% | 9 | SFT天花板 |

**总均分 31.3%** (v2.17b: 29.7%)

### 待完成
- [ ] 等评测完成（~30 samples remaining）
- [ ] 拉取完整 JSON 做 liars_dice root cause（think 内容 vs 动作解析）
- [ ] 确认空间游戏 SFT 天花板 → GRPO 提案
- [ ] 已发 P1 报告给 Strategist
