# Data-Game TODO

## 当前任务：v10 数据采样 + 合并

### 采样目标

| 游戏 | medium 原始 | full 原始 | 赢的目标 | Prompt |
|------|-----------|---------|---------|--------|
| othello | 2200 | 2300 | 2000 (1200+800) | eval-aligned |
| hex | 2000 | 1000 | 800 (600+200) | eval-aligned |
| clobber | 2000 | 1600 | 2000 (1200+800) | eval-aligned |
| **总原始** | **6200** | **4900** | **4800** | |

### 算力分配

| 机器 | 可用核 | othello | hex | clobber |
|------|--------|---------|-----|---------|
| m1 | 128 全用 | med 15 + full 10 | med 15 + full 5 | med 10 + full 5 |
| m2 | 128 全用 | med 15 + full 10 | med 15 + full 5 | med 10 + full 5 |
| work1 | 64 一半 | med 8 + full 5 | med 7 + full 3 | med 5 + full 2 |
| work2 | 64 一半 | med 8 + full 5 | med 7 + full 3 | med 5 + full 2 |
| **总进程** | | **76** | **60** | **44** |

### 执行步骤

- [ ] 1. 上传最新 bot 代码到 m1/m2/work1/work2
- [ ] 2. 启动全部 180 进程（所有游戏并行）
- [ ] 3. 监控进度，完成的游戏立即释放进程给未完成的（clobber→hex）
- [ ] 4. 同时做 liars_dice v6 过滤（本地，5 分钟）
- [ ] 5. 全部采样完成后拉取到本地
- [ ] 6. 过滤：赢的 + seed去重 + 最少回合 + think完整 + action合法
- [ ] 7. 合并：v6 原始(goofspiel/leduc/gin) + liars过滤 + 新空间游戏
- [ ] 8. 质量审查
- [ ] 9. 上传 HF canonical
- [ ] 10. 通知 strategist 开始训练

### 过滤规则

**通用**：score>=0.5, seed去重, think完整(>=5词), action纯数字

**othello**：≥20 回合, medium:full=60:40, 候选标注覆盖≥90%
**hex**：≥5 回合, 棋盘 5/7/9/11 各~25%, medium:full=75:25
**clobber**：≥5 回合, medium:full=60:40, rows/cols 多样
**liars_dice**：v6 短游戏(1-2回合)全保留704条 + 长游戏取100条 = ~804条, call≥40%

### 最终数据集

| 游戏 | 条数 | 来源 | Prompt |
|------|------|------|--------|
| goofspiel | 1048 | v6 不动 | v6 |
| leduc_poker | 1069 | v6 不动 | v6 |
| gin_rummy | 1026 | v6 不动 | v6 |
| liars_dice | ~804 | v6 过滤 | v6 |
| othello | ~2000 | 新采样 | eval-aligned |
| hex | ~800 | 新采样 | eval-aligned |
| clobber | ~2000 | 新采样 | eval-aligned |
| **总计** | **~8747** | | |

### 关键改进点（vs v6 原始数据）

1. 空间游戏对手从 random → medium/full MCTS（匹配评测分布）
2. 候选位置标注：每个 MCTS 候选带 [center]/[edge]/[X-square] 等（修复反向学习）
3. 被选 action 客观特征：Flips/Frontier/Stable chain/Bridge 等（辅助概念泛化）
4. liars_dice call 比例从 34% 提升到 ~45%（修复 bid 偏移）

### 目标时间

3 小时内完成采样。瓶颈是 hex full（赢率 20%，每条 ~7min）。
