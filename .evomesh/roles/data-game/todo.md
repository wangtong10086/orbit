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

## 阶段 3: 小批量数据集审查 ✅ 完成
- [x] 1020条审查：0格式错误，100% think block，全部 winning
- [x] 过滤方案：只保留 winning games (score >= 0.5)
- [x] 生成方案：MCTS bot vs random，降低 sim 数保证速度
- [x] 目标：每游戏 500 条，总 3500 条
- [ ] 发消息给 Strategist 确认方案

## 阶段 4: 最终数据集生成 ← 当前阶段
**双机并发生成** (m1: 快游戏, m2: 慢游戏)

### m1 (完成 + 进行中)
- [x] goofspiel: ~945 条 ✅
- [x] leduc_poker: ~536 条 ✅
- [ ] liars_dice: ~196 条 (MCTS 10000sim, ~6s/seed)
- [ ] gin_rummy: 生成中 (MCTS 2000sim, ~60s/seed)

### m2 (刚启动)
- [ ] othello: 生成中 (MCTS 3000sim/20r)
- [ ] hex: 生成中 (MCTS 3000sim/50r)
- [ ] clobber: ~5 条 (MCTS 5000sim/20r)

### 完成后
- [ ] 从 m2 下载数据到 m1
- [ ] 合并所有游戏 → canonical
- [ ] HF sync

## 阶段 5: 更新所有文档
前置: 阶段 4 完成
