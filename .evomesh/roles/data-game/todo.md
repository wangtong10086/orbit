# Data-Game TODO

## 阶段 1-3: ✅ 完成
Bot 优化 + Think 审查 + 格式审查 全部完成。

## 阶段 4: 数据生成 ✅ Canonical 已更新

**v11 Canonical: 4462 entries** (旧 v10 2260 条已归档)

| 游戏 | 条数 | Bot | Think | 状态 |
|------|------|-----|-------|------|
| goofspiel | 953 | 规则 95% | v5 | ✅ |
| leduc_poker | 525 | 规则 60% | v5 | ✅ |
| liars_dice | 1000 | MCTS 10000sim 80% | v5 | ✅ |
| clobber | 998 | MCTS 5000sim 80% | v4 | ✅ |
| othello | 325 | MCTS 3000sim 60% | v5 | 🔄 继续收集 |
| hex | 89 | MCTS 3000sim 60% | v4 | 🔄 继续收集 |
| gin_rummy | 572 | MCTS 2000sim 80% | v2 | 🔄 继续收集 |

**后台继续生成** othello/hex/gin_rummy，drafts 目录持续更新。
训练后根据 eval 结果决定是否补充特定游戏。

## 阶段 5: 等待训练结果
- [ ] 训练完成后分析 per-game eval 得分
- [ ] 得分低的游戏针对性补充数据
- [ ] 考虑 GPT-5.4 rewrite 提升 think 多样性（如需要）
