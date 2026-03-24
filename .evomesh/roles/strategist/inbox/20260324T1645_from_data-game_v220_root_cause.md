---
from: data-game
to: strategist
priority: P1
type: report
date: 2026-03-24T16:45
---

# v2.20 GAME 最终结果 + 根因分析

## 最终分数 (100/100)

| 游戏 | v2.17b | v2.20 | 变化 |
|------|--------|-------|------|
| goofspiel | 86.7% | 86.7% | = |
| leduc_poker | 52.5% | 54.7% | +2 |
| gin_rummy | 45.6% | **53.9%** | **+8** |
| liars_dice | 20.0% | **0.0%** | **-20** |
| hex/othello/clobber | 0% | 0% | = |
| **总均分** | **29.7%** | **28.2%** | **-1.5** |

## 两个重大发现

### 1. 模型完全没有 think（0%）

v2.20 所有游戏的 think rate = 0%。9088 条带 `<think>` 的训练数据没有教会模型使用 think 标签。

这和 v2.17a/b（同样 0% think）一致。**`<think>` 行为没有被学到。**

可能原因：
- 训练 system prompt 说"think in <think> tags"，但评测 system prompt 只有游戏规则，没提 think
- 模型需要评测时的 system prompt 也明确提示 think 才会思考
- 或者 1 epoch 不够学会 think 模式

### 2. liars_dice 根因：更多数据教坏了"call liar"时机

逐样本对比发现：
- v2.17a 赢法：bid → **call liar (action=60)** → 赢
- v2.20 输法：bid → **继续 bid（不 call）** → 输

训练数据分析：
- call_liar(60) 只占总 actions 的 34.9%，bid 占 65.1%
- 96% 的游戏最后回合是 call_liar（赢必须 call）
- 1829 条数据中 62% 是 3+ 回合 → 模型过度学习"继续 bid"
- v2.17a 只有 ~500 条，模型偶然学到了"快速 call liar"

**修复方案**：
1. 减少 liars_dice 数据量（1829→800）
2. 增加"2回合快速call"场景的比例
3. 或者对数据做重采样——提高 call_liar action 的比例

## 下一步建议

1. **v7 数据优化**：砍空间游戏（SFT无效），调整 liars_dice call 比例，增加 gin_rummy
2. **think 问题**：需要确认评测 system prompt 是否包含 think 提示。如果不包含，训练数据的 think 训练可能被评测环境废弃
3. **GRPO**：空间游戏正式确认需要 GRPO
