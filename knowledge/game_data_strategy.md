# GAME 数据生成策略

## 目标：GAME 均分 50%

当前最好 29.7%（v2.23）。竞对 47%。

## 已验证事实

| # | 事实 | 证据 |
|---|------|------|
| 1 | v6 prompt("think first") 对 gin 比 v8("only action") 好 11% | v2.20 gin=54% vs v2.23 gin=43% |
| 2 | liars_dice 数据多反而差：1829条→0%, ~500条→20% | v2.20 vs v2.17b |
| 3 | liars_dice 是唯一评测时 think 的游戏（内容类型触发） | 控制变量实验 |
| 4 | 空间游戏评测时不 think（棋盘内容不触发） | 控制变量实验 |
| 5 | think 内容在训练时影响 action 质量（训练信号） | gin 54% 来自 MCTS think 数据 |
| 6 | 数据总量减少伤害所有游戏 | v7(8259) 全面退步 |
| 7 | 空间游戏 action 全合法但策略差 | eval 轨迹分析 |
| 8 | 训练 vs-random 评测 vs-MCTS = 状态分布不匹配 | 理论+观察 |
| 9 | 空间游戏 98% think 是 MCTS stats 复述，不教可迁移策略 | 数据分析 |
| 10 | 替换 think 为模板化规则 → 多样性从 96% 降到 1%（v9 失败） | v9 草稿审查 |

## 各游戏方案

### goofspiel（87% → 90%）
- 保持 v6 原始 1048 条不变
- 已接近上限，不花精力

### leduc_poker（55% → 65%）
- 保持 v6 原始 1069 条
- **追加** 1000 条新数据（vs-MCTS 对手，匹配评测条件）
- 总量 ~2000 条

### gin_rummy（54% → 65%）
- 保持 v6 原始 1026 条
- **追加** 1000 条新数据（vs-MCTS 对手）
- 总量 ~2000 条

### liars_dice（20% → 40-50%）
- v6 原始 1829 条 → **后处理**缩减到 ~800 条
- call_liar(60) 在 action 中占比 ≥ 40%（通过筛选平衡）
- 不重新生成，只过滤已有数据
- 模型评测时会 think（Step 格式），think 质量已验证有效

### othello（0% → 25-30%）
- **重新生成**：修改 `_get_game_context()` 让每步都有策略分析
- Think 格式：**MCTS stats 保留（多样性）+ game_context 追加（策略）**
- **无 random 对手**：medium MCTS(300sim) 60% + full MCTS(eval级) 40%
- 目标 2000 条（需生成 ~4000 条原始数据，赢率 40-60%）
- game_context 内容：位置名、翻转数、frontier 数、corner/edge/X-square 分析

### hex（0% → 20-25%）
- 同 othello：重新生成 + 增强 game_context
- **无 random 对手**：medium 60% + full 40%
- game_context：bridge 分析、chain 状态、path cost、edge 连接
- 按棋盘大小分层（5×5 多采样，状态空间小更易学）
- 目标 2000 条

### clobber（0% → 20-25%）
- 同 othello：重新生成 + 增强 game_context
- **无 random 对手**：medium 60% + full 40%
- game_context：safe capture、mobility 变化、parity
- 目标 2000 条

## 数据总量

| 游戏 | v6 原始 | 新方案 | 来源 |
|------|---------|--------|------|
| goofspiel | 1048 | 1048 | v6 不变 |
| leduc_poker | 1069 | ~2000 | v6 + 追加 |
| gin_rummy | 1026 | ~2000 | v6 + 追加 |
| liars_dice | 1829 | ~800 | v6 过滤 |
| othello | 1358 | ~2000 | 重新生成 |
| hex | 1211 | ~2000 | 重新生成 |
| clobber | 1547 | ~2000 | 重新生成 |
| **总计** | **9088** | **~11848** | |

## 空间游戏 think 增强的原则

**不替换，只追加。** MCTS stats 保留多样性，game_context 追加策略性。

```
format_mcts_think() 输出：
"Evaluated 4 options: d3 (48%, 856), e6 (48%, 757)... Choosing d3."

_get_game_context() 追加（改为每步都返回）：
"Playing d3. Central position, flips 1 piece. 3 frontier cells. No corner risk."

最终 think：
"Evaluated 4 options: d3 (48%, 856)... Choosing d3. Playing d3. Central position, flips 1."
```

## System Prompt

全部使用 v6 prompt："First, think through your strategy inside <think> tags. Then output ONLY the action ID."

不使用 v8 eval-aligned prompt（已证实伤害 gin -11%）。

## game_context 增强设计

MCTS stats think 保留不变。只在 `_get_game_context()` 中追加每步的客观分析。

### othello（每步 5 个维度）
位置名 + 位置类型(corner/edge/center/X/C) + 翻转数 + frontier 数 + corner 风险

### hex（每步 4 个维度）
位置名 + bridge 检测 + chain 长度 + path cost 变化

### clobber（每步 3 个维度）
action 描述 + safe capture 检测 + mobility 变化

**原则**：只用可精确计算的客观事实，不做主观判断。

## 自我攻击结论

game_context 增强是**低确信度低成本**改动（P2）。核心驱动力是 v6 prompt（P0）+ liars 平衡（P0）+ 更多数据（P1）+ vs-MCTS 匹配（P1）。

50% 目标的诚实评估：P0+P1 预期 40-45%，P2 可能 +5%。到 50% 需要空间游戏 25-30%，无 SFT 验证先例。

## 执行步骤

1. liars_dice v6 数据后处理（缩减 + call 平衡）— 最快
2. 修改 othello/hex/clobber `_get_game_context()` — 增强不替换
3. 重新生成空间游戏数据（vs-random 60% + vs-MCTS 40%）
4. 追加 leduc/gin 数据（vs-MCTS 对手）
5. 合并：v6 原始(goofspiel/leduc/gin) + 新空间游戏 + liars 过滤 + leduc/gin 追加
6. 质量审查 → canonical → HF
