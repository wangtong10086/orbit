# Data-Game TODO

## 当前任务：准备 v10 数据集

目标 GAME 均分 50%。详细策略见 `knowledge/game_data_strategy.md`。

### 执行清单

- [ ] 修改 othello `_get_game_context()` — 每步返回策略分析
- [ ] 修改 hex `_get_game_context()` — 每步返回策略分析
- [ ] 修改 clobber `_get_game_context()` — 每步返回策略分析
- [ ] 重新生成 othello 2000 条（vs-random 60% + vs-MCTS 40%）
- [ ] 重新生成 hex 2000 条（同上）
- [ ] 重新生成 clobber 2000 条（同上）
- [ ] 追加 leduc_poker 1000 条（vs-MCTS 对手）
- [ ] 追加 gin_rummy 1000 条（vs-MCTS 对手）
- [ ] liars_dice v6 数据后处理：1829 → 800 条 + call≥40%
- [ ] 合并全部数据 → canonical game.jsonl（~11848 条）
- [ ] 质量审查
- [ ] 上传 HF

### 数据配方

| 游戏 | 来源 | 条数 | System Prompt |
|------|------|------|--------------|
| goofspiel | v6 不变 | 1048 | v6 "think first" |
| leduc_poker | v6 + 追加 | ~2000 | v6 "think first" |
| gin_rummy | v6 + 追加 | ~2000 | v6 "think first" |
| liars_dice | v6 过滤 | ~800 | v6 "think first" |
| othello | 重新生成 | ~2000 | v6 "think first" |
| hex | 重新生成 | ~2000 | v6 "think first" |
| clobber | 重新生成 | ~2000 | v6 "think first" |
| **总计** | | **~11848** | |

### 空间游戏 think 增强原则

MCTS stats 保留 + game_context 追加。不替换。
