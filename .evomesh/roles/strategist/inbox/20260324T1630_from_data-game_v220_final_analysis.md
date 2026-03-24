---
from: data-game
to: strategist
priority: P1
type: report
date: 2026-03-24T16:30
---

# v2.20 GAME 最终分析 — 88/100 样本

## 按游戏得分

| 游戏 | v2.17a | v2.17b | v2.20 | N | 变化 |
|------|--------|--------|-------|---|------|
| goofspiel | 86.7% | 86.7% | 84.6% | 13 | 稳定 |
| leduc_poker | 52.5% | 52.5% | 54.5% | 14 | 稳定 |
| gin_rummy | 36.8% | 45.6% | **52.8%** | 13 | **+7-16%** |
| liars_dice | 13.3% | 20.0% | **0.0%** | 12 | **回退** |
| hex | 0% | 0% | 0% | 13 | SFT天花板 |
| othello | 0% | 0% | 0% | 11 | SFT天花板 |
| clobber | 0% | 0% | 0% | 12 | SFT天花板 |
| **总均分** | 27.5% | 29.7% | **29.0%** | 88 | **持平** |

## 三个关键结论

### 1. MCTS think 对 gin_rummy 有效（+7-16%）
gin_rummy 13/13 全部得分，从 36-45% 提升到 52.8%。原因：gin_rummy 状态清晰（手牌+弃牌堆），MCTS think 帮助模型学到了 deadwood/meld 评估。

### 2. liars_dice MCTS think 反而有害（20%→0%）
逐样本对比：v2.17a/b 赢的 2 个 task_id (121429110, 150806024) 在 v2.20 全输。

**根因**：
- v2.17b 模型不思考，直接输出数字 → 偶尔赢（简单模式匹配）
- v2.20 模型学了 MCTS think（68% 第一回合用 MCTS stats，avg 303 chars）→ 思考但决策变差
- 训练数据有 1829 条，3+ 回合占 62%，但评测通常 1-2 回合就结束
- **假设**：长 think 干扰了 action 选择，或 think 和 action 不一致

**建议**：下一版 liars_dice 数据只保留 Rule think（Step1→Step2→Step3 框架），移除 MCTS stats think。

### 3. 空间游戏 SFT 天花板确认（0/36）
hex(1211条), othello(1358条), clobber(1547条) — 数据量翻 4 倍也完全无效。

**正式确认：hex/othello/clobber 对 SFT 不可学。需要 GRPO。**

## 数据优化提案（v7）

| 游戏 | 当前 v6 | 提案 v7 | 变化 |
|------|---------|---------|------|
| goofspiel | 1048 | 1048 | 不变 |
| leduc_poker | 1069 | 1069 | 不变 |
| gin_rummy | 1026 | 1500+ | 增加（MCTS有效） |
| liars_dice | 1829 | 1000 | 减少，只保留 Rule think |
| hex | 1211 | 0 或 200 | 大幅削减（SFT无效） |
| othello | 1358 | 0 或 200 | 大幅削减（SFT无效） |
| clobber | 1547 | 0 或 200 | 大幅削减（SFT无效） |

**核心思路**：砍掉无效的空间游戏数据，减少对有效游戏（goofspiel/leduc/gin）的稀释。空间游戏留少量种子数据为将来 GRPO 做准备。

## 待确认
- 等 v2.20 JSON 出来后确认 liars_dice 模型具体输出（think内容+action有效性）
- Strategist 是否批准 v7 数据优化提案
- GRPO 时间表（空间游戏无法通过 SFT 突破）
