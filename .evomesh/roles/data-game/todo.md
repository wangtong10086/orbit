# Data-Game TODO

## 目标：GAME 50 分

当前最好 29.7%（v2.23 noreason = v2.17b 水平）。竞对 47%。

## 已验证的事实（不可推翻）

| # | 事实 | 证据 |
|---|------|------|
| 1 | v6 prompt("think first") 对 gin_rummy 比 v8 prompt("only action") 好 11% | v2.20 gin 54% vs v2.23 gin 43% |
| 2 | liars_dice 数据量越多反而越差：1829→0%, ~500→20% | v2.20 vs v2.17b |
| 3 | liars_dice 是唯一在评测时 think 的游戏 | 直接 API 验证 |
| 4 | 空间游戏在评测时不 think（内容类型触发，非格式问题） | 控制变量实验 |
| 5 | think 内容在训练时作为学习信号有效（即使评测不输出） | gin 54% 的 MCTS think 数据 |
| 6 | 空间游戏 action 全合法但策略差，中盘输 | v2.20 eval 轨迹分析 |
| 7 | 数据总量减少伤害所有游戏 | v7(8259) 全面退步 vs v6(9088) |
| 8 | vs-random 训练 vs vs-MCTS 评测 = 分布不匹配 | 理论分析 |

## 自我攻击记录

### 攻击："改 think 格式为 Step 就能让空间游戏 think"
**结论：错。** 控制变量证明是内容类型触发 think，不是格式。换 Step 不会让 othello think。

### 攻击："让模型 think 就能提高空间游戏分数"
**结论：不确定。** othello 在 standalone eval 中 think 了 8/32 回合但仍 0 分。Think 集中在终局，前 24 回合不 think 已经输了。即使全程 think，think 质量能否赢 MCTS 也未验证。

### 攻击："增强 _get_game_context 让 think 有更多规则会提分"
**结论：不确定。** v2.17b（旧 think 格式）和 v2.20（MCTS stats think）分数接近。Think 质量的影响没有和数据量/prompt 格式区分开。可能有帮助但优先级不是最高。

### 攻击："v6 prompt 比 v8 好"
**结论：部分正确。** gin 54→43 强证据。但 v2.17b(v6 prompt, 5584 data)=29.7% vs v2.20(v6 prompt, 9088 data)=28.2%，更多数据反而低 1.5%——因为 liars 回退抵消了 gin 提升。不是 prompt 本身的问题，是 liars 数据量的问题。

### 攻击："大量增加 vs-MCTS 数据就能提分"
**结论：不确定。** 理论合理（匹配 eval 分布），但没有实验证据。vs-MCTS 数据赢率低(30-60%)，数据量受限。可能帮助有限。

## 已确认的最高杠杆改动

### 1. liars_dice 数据量控制 + call 比例（置信度：高）
- **问题**：1829 条数据中 bid 65% / call 35% → 模型过度学习 bid → 0%
- **证据**：v2.17b 只有 ~500 条时 call 比例自然 → 20%
- **方案**：liars_dice 保留 ~800 条，确保 call_liar(60) 在 action 中占 40%+
- **预期**：恢复到 20%，可能更高（think 质量好）

### 2. 使用 v6 prompt（置信度：高）
- **问题**：v8 eval-aligned prompt 矛盾训练信号 → gin 退步 11%
- **证据**：v2.20(v6)=gin 54% vs v2.23(v8)=gin 43%
- **方案**：回到 v6 prompt "First, think through your strategy inside <think> tags"
- **预期**：gin 恢复到 54%+

### 3. 保持数据总量 9088+（置信度：高）
- **问题**：减少数据伤害所有游戏
- **证据**：v7(8259) 全面退步
- **方案**：总量不低于 9088。liars 减少的量用其他游戏补

### 4. 空间游戏 vs-MCTS 数据（置信度：中）
- **问题**：训练 vs-random 但评测 vs-MCTS = 状态分布不匹配
- **证据**：理论合理，无实验验证
- **方案**：混合 vs-random + vs-MCTS 数据
- **风险**：vs-MCTS 赢率低，数据量受限

### 5. 增强 think 策略内容（置信度：中低）
- **问题**：98% MCTS stats think 不教可迁移策略
- **证据**：无直接证据证明改善 think 内容能提分
- **方案**：在 MCTS stats 后追加 game_context（corner/edge/mobility 分析）
- **风险**：可能无效，之前的 rule-think bot 替换也没证明有效

## 建议执行顺序

**Phase 1（只改确定有效的，最小改动）：**
1. 回到 v6 prompt（全部游戏）
2. liars_dice 数据缩减到 800 条 + call 比例 40%+
3. 其他游戏保持 v6 原始数据不变
4. 总量 ~8000+
→ 预期：gin 54%，liars 20-30%，其他不变 → ~32-35%

**Phase 2（Phase 1 验证后）：**
5. 增加 gin_rummy/leduc_poker 数据量（已证明更多数据帮 gin 提分）
6. 空间游戏混入 vs-MCTS 数据
7. 增强 think game_context
→ 预期：gin 60%+, leduc 60%+, 空间可能 10-20% → ~40-45%

**Phase 3（Phase 2 验证后）：**
8. 精细调整每个游戏的数据比例
9. 考虑多 epoch 或不同 lr
→ 预期：接近 50%

## 待验证的关键假设

- [ ] v6 prompt + liars 800 条 = liars 20%+ 且 gin 54%+
- [ ] vs-MCTS 数据能否提升空间游戏
- [ ] think context 增强能否提升 action 质量
