# Data-Game TODO

## 阶段 1: 极限优化 Bot 策略 ✅ 完成

| 游戏 | Minimax | MCTS Bot (10局) | Bot版本 | MCTS配置 |
|------|--------|----------------|--------|---------|
| goofspiel | 95% | — | v2 rule | random opponent |
| leduc_poker | 60% | — | v2 rule | 3000/200r opponent |
| gin_rummy | 50% | **80% (8/10)** | v2 MCTS | 2000sim/20r vs 500/10r |
| othello | 20% | **60% (6/10)** | v4b MCTS | 3000sim/20r vs 1000/20r |
| hex | 30% | **60% (6/10)** | v7b MCTS | 3000sim/50r vs 1000/50r |
| liars_dice | 0% | **80% (8/10)** | v2 MCTS | 10000sim/50r vs 3000/200r |
| clobber | 0% | **80% (8/10)** | v4 MCTS | 5000sim/20r vs 1500/100r |

## 阶段 2: 审查 Think 链质量 ✅ 完成
- [x] 每游戏 winning 轨迹审查 (goofspiel/leduc/gin_rummy/othello/hex/liars_dice/clobber)
- [x] 所有游戏 think 包含具体策略推理和量化数据
- [x] othello v3c: board stats + stability + frontier (比 v2 大幅改进)
- [x] gin_rummy: deadwood数字偶尔不一致但整体教学价值高

## 阶段 3: 小批量数据集审查
前置: 阶段 2 完成
- [ ] 每游戏 50 条: 格式/质量/胜率/过滤方案
- [ ] 是否过滤低分? 是否补 random?
- [ ] 完成后给 Strategist 发消息确认数据方案，等批准后进入阶段 4

## 阶段 4: 最终数据集生成 (每游戏 1000 条)
前置: 阶段 3 完成
- [ ] 并发采样, 两台 GPU
- [ ] 备份旧数据集, 仅保留高质量 bot 数据
- [ ] 此前生成的数据全部废弃
- [ ] canonical → HF sync

## 阶段 5: 更新所有文档
前置: 阶段 4 完成
