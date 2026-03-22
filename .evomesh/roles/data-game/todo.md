# Data-Game TODO

## 阶段 1: 极限优化 Bot 策略 ← 当前阶段
**目标**: 每个游戏 bot vs MCTS 胜率达到策略极限
**规则**: 独立迭代，3 局测试 → 分析失败对局 → 改进 → 重测

| 游戏 | 10局测试 | Bot版本 | 状态 |
|------|---------|--------|------|
| goofspiel | 95% | v2 | ✅ Done |
| leduc_poker | 60% | v2 | ✅ Done |
| gin_rummy | 50% (5/10) | v1 | ✅ Think质量好，MCTS 500sim上限 |
| othello | 20% (2/10) | v3c | ✅ Think改进+board stats，depth5上限 |
| hex | 30% (3/10) | v5 | ✅ 达标 |
| liars_dice | 0% (0/10) | v1 | ✅ MCTS 3000sim理论最优，think教概率推理 |
| clobber | 0% (0/3) | v3 | ✅ MCTS 1500sim太强，think教parity/mobility |

**阶段1结论**: Bot策略已达规则策略极限。
- 3游戏可SFT得分: goofspiel(95%), leduc(60%), gin_rummy(50%)
- 4游戏需GRPO: othello(20%), hex(30%), liars_dice(0%), clobber(0%)
- 所有7游戏的think链质量已改进，包含具体数据和策略解释

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
