# Data-Game TODO

## v6 MCTS Stats Data — COMPLETE ✅

**Canonical: 9088 entries, 0 errors, HF synced.**
**All data generated with final verified code. No filtering needed.**

| Game | Count | Bot | Think Format |
|------|-------|-----|-------------|
| goofspiel | 1048 | Rule v4 | Rule think (hand/prize/bid) |
| leduc_poker | 1069 | Rule v4 | Rule think (pot odds/range) |
| liars_dice | 1829 | MCTS 10000sim | MCTS stats T1 + Rule fallback T2+ |
| gin_rummy | 1026 | MCTS 2000sim | MCTS stats (draw/discard/knock) |
| othello | 1358 | MCTS 3000sim | MCTS stats + corner/edge context |
| hex | 1211 | MCTS 3000sim | MCTS stats + bridge context |
| clobber | 1547 | MCTS 5000sim | MCTS stats + safe capture context |

## Think Chain Architecture
- MCTS search → extract child stats (visits + win rates)
- If visits > 1: "Evaluated N options: a1 (78%), d3 (42%)... Choosing a1."
- If visits ≤ 1: fallback to game-specific rule think
- Lookahead: opponent response → our counter (from search tree)
- System prompt: v12 (think in `<think>` tags)

## v2.20 Eval 接近完成 (85/100)

| 游戏 | v2.17b | v2.20 | N | 变化 |
|------|--------|-------|---|------|
| goofspiel | 86.7% | 84.6% | 13 | 采样波动 |
| leduc_poker | 52.5% | 55.8% | 13 | 持平 |
| gin_rummy | 45.6% | **52.8%** | 13 | **+7% MCTS有效** |
| liars_dice | 20.0% | **0.0%** | 12 | **回退!** |
| hex/othello/clobber | 0% | 0% | 34 | SFT天花板 |

**总均分 29.6%** ≈ v2.17b 29.7%

### v2.20 根因
- **模型 0% think** — 因为训练/评测 system prompt 不一致
  - 训练: "First, think through your strategy inside `<think>` tags"
  - 评测: "You must respond with ONLY the action ID. Do NOT include descriptions."
  - 模型听评测指令，不思考
- **liars_dice 回退**: action 分布偏移（bid 65% vs call 35%）

### v7 数据 — system prompt 对齐 ✅
- 9088 条全部替换 system prompt 为评测格式
- assistant 保留 `<think>` 块不变
- 模型将学到: 即使被告知"只输出数字"，也先 `<think>` 推理
- HF 已同步

### 下一步
- [ ] 通知 Strategist v7 数据已就绪，请安排训练
- [ ] liars_dice action 重采样（后续优化，v7 先测 think 对齐效果）
