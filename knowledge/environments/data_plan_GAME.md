# GAME 数据计划与深度分析

> 最后更新: 2026-03-18 16:15 UTC | 优先级: P1 | 状态: v2 训练中 + v3 staging 就绪

## 1. 环境概述

GAME 环境评估 LLM 在 OpenSpiel 棋牌游戏中的对弈能力。scheduling_weight=3.0 意味着采样频率是其他环境的 3 倍（更多数据点，但评分权重与其他环境一致）。

**评分**: win=1.0, draw=0.5, loss=0.0，所有样本平均。300 样本评估。
**格式**: system prompt → 多轮 user(game state + legal actions) → assistant(action ID)
**解析**: `strip_think_tags=True`，提取纯整数。2 次重试。非整数=0 分。

## 2. 当前数据状态

### 2.1 总体分布 (canonical: 2641 条)

| 游戏 | 条数 | 占比 | 可学性 | 来源构成 |
|------|------|------|--------|---------|
| goofspiel | 1050 | 39.8% | Solved (100%) | 741 distill + 129 bot + 180 无标注 |
| gin_rummy | 505 | 19.1% | Bot-improved | 147 bot + 358 无标注 |
| leduc_poker | 428 | 16.2% | Strong | 285 distill + 96 bot + 47 无标注 |
| liars_dice | 333 | 12.6% | Zero (SFT无效) | 全部无标注 |
| hex | 190 | 7.2% | Zero | 全部无标注 |
| clobber | 123 | 4.7% | Zero | 全部无标注 |
| othello | 12 | 0.5% | Zero | 全部无标注 |

**来源缺失**: 47% 的条目（1243/2641）缺少 `source` 字段，全部来自 DDB/HF 恢复数据。

### 2.2 消息结构深度分析

| 游戏 | 平均轮数 | 平均 tokens | 最大 tokens | 特征 |
|------|---------|------------|------------|------|
| gin_rummy | 32 轮 | ~6,900 | ~17,800 | 最长，变化大 |
| othello | 30.5 轮 | ~3,100 | ~3,400 | 长对局但数量极少 |
| hex | 12.8 轮 | ~2,200 | ~6,400 | 中等 |
| goofspiel | 11.2 轮 | ~1,200 | ~2,000 | 稳定 |
| clobber | 10.9 轮 | ~1,600 | ~2,600 | 稳定 |
| liars_dice | 2.8 轮 | ~400 | ~900 | 极短 |
| leduc_poker | 2.6 轮 | ~440 | ~650 | 极短 |

**关键发现**: 游戏间 token 消耗差异巨大 (440 vs 6900)。gin_rummy 一条数据相当于 15 条 leduc_poker。训练时 packing 效率受此影响。

### 2.3 分数分布

| 游戏 | 全胜(1.0) | 平均分 | 特征 |
|------|----------|--------|------|
| goofspiel | 100% | 1.0 | 纯胜利数据 |
| clobber | ~100% | 1.0 | 纯胜利 |
| hex | ~100% | 1.0 | 纯胜利 |
| liars_dice | ~100% | 1.0 | 纯胜利 |
| othello | 100% | 1.0 | 纯胜利 |
| leduc_poker | 变化大 | 0.68 | 0.31-1.0 连续分布 |
| gin_rummy | 56% 平局 | 0.72 | 仅 11 条=1.0，多数 0.5-0.8 |

**问题**: 数据严重偏向胜利。模型学不到逆境中的最优决策。gin_rummy 和 leduc_poker 含低分数据，可能教会模型次优策略。

### 2.4 Think Tag 使用

| 游戏 | Think 率 | 一致性 |
|------|---------|--------|
| leduc_poker | 93.2% | 高 |
| goofspiel | 88.6% | 较高 |
| clobber | 75.6% | 中 |
| hex | 74.2% | 中 |
| liars_dice | 72.7% | 中 |
| gin_rummy | 56.6% | **低** |
| othello | 41.7% | **很低** |

**问题**: Think tag 使用不一致。同一游戏内混合 think/no-think 会混淆模型。eval 的 `strip_think_tags=True` 意味着有无 think 不影响评分，但训练中不一致格式可能降低学习效率。

### 2.5 格式质量问题

发现 **10 条异常数据**:
- gin_rummy: 8 条含非法 assistant 输出（如 `).34`, 数字后跟解释文本）
- goofspiel: 2 条含非法输出（如 `.3`, `.1`）

**影响**: 这些条目会教模型输出非整数 → parse error → 0 分。应移除。

## 3. 瓶颈根因分析

### 3.1 结构性瓶颈: SFT 对 Zero-tier 游戏无效

| 证据 | 含义 |
|------|------|
| othello/hex/liars_dice/clobber 多版本训练均 0% | SFT 无法学会这些游戏的策略 |
| 这 4 个游戏占数据 24.9% | 近 1/4 训练预算浪费 |
| 竞品在这些游戏上也表现差 | 行业性难题 |

**根因**: 这些游戏需要搜索/前瞻能力，SFT 只能模仿表面模式。DPO/RL 是唯一出路。

### 3.2 数据偏差: 只有胜利轨迹

几乎所有数据 score≥0.5（只保留 bot 赢的对局）。模型缺乏:
- 从劣势恢复的能力
- 评估风险-收益的能力
- 对手强势时的防守策略

### 3.3 leduc_poker 数据饱和

从 600 次生成中仅得 58 条唯一数据。原因: leduc_poker 只有 6 张牌（3 花色 × 2 等级），游戏状态空间极小。进一步 bot 生成 ROI 为零。

## 4. v3 Staging 数据

| 文件 | 游戏 | 新增 | 已有 → 合并后 |
|------|------|------|-------------|
| `data/game_v3_bot_goofspiel.jsonl` | goofspiel | 192 | 1050 → 1242 |
| `data/game_v3_bot_gin_rummy.jsonl` | gin_rummy | 440 | 505 → 945 |
| `data/game_v3_bot_leduc_poker.jsonl` | leduc_poker | 58 | 428 → 486 |

合并后 learnable 占比: 75.1% → 80.2%。配合降采样: 89.9%。

## 5. 行动计划

### v2 (当前): 训练中，不修改
- 2641 条，seq=8192
- 预期: GAME 25-35

### v2a (如果 v2 eval 发现问题):
| 行动 | 条件 | 预期效果 |
|------|------|---------|
| 移除 10 条格式异常 | 立即 | 消除 parse error poison |
| 合并 v3 staging (+690) | Strategist 批准 | learnable 80.2% |
| Zero-tier 降采样 658→300 | Strategist 批准 | learnable 89.9% |

### v3 (DPO):
- 589 对偏好对已就绪
- 优先 gin_rummy 和 leduc_poker（有分数梯度，适合偏好学习）
- Zero-tier 需要 RL/MCTS，SFT/DPO 均不够

### 长期研究方向:
1. **per-game 自适应策略**: 不同游戏用不同训练方法（SFT for learnable, RL for zero-tier）
2. **对手建模数据**: 加入对手策略多样性（不只 random opponent）
3. **失败轨迹**: DPO rejected samples 来自 bot 输的对局

## 6. 质量检查清单

- [x] Schema: `{"messages": [...], "env": "GAME", "score": float}`
- [x] 最后消息 role=assistant
- [x] `game` 字段 100% 覆盖
- [x] 仅含 7 个活跃游戏
- [x] 去重 (full-message MD5)
- [x] HF 已同步
- [ ] 移除 10 条格式异常 (v2a)
- [ ] 补齐 47% 缺失的 `source` 字段

## 7. 关键文件

| 文件 | 条数 | 状态 |
|------|------|------|
| `data/canonical/game.jsonl` | 2,641 | v2 训练中 |
| `data/game_v3_bot_*.jsonl` | 690 | v3 staging |
| `scripts/game_bot_gen.py` | — | 程序化 bot 生成 |
| `scripts/game_gen.py` | — | LLM 蒸馏 (需 affinetes) |
| `repos/affinetes/environments/openspiel/` | — | eval 源码参考 |
