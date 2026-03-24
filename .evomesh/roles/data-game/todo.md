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

### 根因分析（JSON 确认）
- **模型 0% think** — 所有游戏都没有 `<think>` 输出，和 v2.17a/b 一致
- **liars_dice**: 不是 think 干扰，是 action 策略退化。更多数据(1829)教会了"持续bid"而遗忘了"call liar"。call_liar 仅占 34.9% actions
- **空间游戏**: 4x 数据无效，SFT 天花板确认

### 下一步
- [ ] 等 Strategist 批准 v7 数据优化提案
- [ ] liars_dice 数据重采样：提高 call_liar 比例 / 增加 2 回合快速 call 场景
- [ ] 确认评测 system prompt 是否提示 think（如果不提示，think 训练可能无效）
- [ ] 空间游戏 GRPO 方案
