# GAME 数据方案

> 最后更新: 2026-03-18 | 优先级: P1 (结构性天花板) | v1 状态: 训练中

## 现状

| 指标 | 值 |
|------|-----|
| canonical 条数 | 1,415 |
| v1 用量 | 1,415 (全量) |
| 历史分数 | 22.6 (v11), 39% non-zero |
| 竞品最高 | 50.75 (affshoot) |
| GM 贡献潜力 | 22.6→40 = **+4.5 GM** |
| 数据格式 | multi-turn (system + user/assistant), assistant = think + action ID |
| 游戏覆盖 | 7/22+ 游戏 (缺 4 个 Strong-tier) |

## 评估格式详解 (源码: affinetes)

### 消息结构
```
System: "You are playing {game}. Respond with the action ID only."
User: "{game_state}\nLegal actions:\n0 -> action_a\n1 -> action_b\n..."
Assistant: "<think>reasoning</think>\n2"  (或直接 "2")
User: "{new_game_state}\nLegal actions:\n..."
...重复直到游戏结束
```

### 输出解析
- eval 用 `strip_think_tags=True` 自动剥离 `<think>` 块
- 最终提取纯整数 (action ID)
- **2 次重试机制**: 解析失败时给第二次机会
- 非整数输出 = parse error → 0 分

### 评分算法
- 每局: win=1.0, draw=0.5, loss=0.0
- 最终分数 = 所有样本得分的平均值
- 100 样本评估, timeout=7200s, concurrency=4

### Task ID 结构
- 格式: `game_idx * 100_000_000 + config_id`
- 例: game_idx=2 (leduc_poker), config=12345 → task_id=200012345
- 训练中的 game_idx: [0,1,2,3,4,6,7,8,9]

### Eval 参数
- Temperature: 0.7
- Memory: 2GB
- Docker image: openspiel:eval
- `--concurrency 4 --timeout 7200` (旧 600s timeout 会漏掉长游戏)

## 游戏分布 (审计结果)

| 游戏 | 条数 | 占比 | 可学性 | game_idx |
|------|------|------|--------|----------|
| gin_rummy | 430 | 30.4% | Bot-improved (0%→100%) | — |
| liars_dice | 327 | 23.1% | Zero (SFT 无效) | — |
| goofspiel | 273 | 19.3% | Solved (100%) | — |
| hex | 206 | 14.6% | Zero (SFT 无效) | — |
| clobber | 120 | 8.5% | Zero (SFT 无效) | — |
| leduc_poker | 47 | 3.3% | Strong | — |
| othello | 12 | 0.8% | Zero (SFT 无效) | — |

**严重问题**:
- 4 个 Strong-tier 游戏完全缺失: hearts, bridge, blackjack, euchre
- 53.6% 数据是 SFT 无法学习的游戏 (liars_dice + hex + clobber + othello = 665 条)
- leduc_poker 仅 47 条, 与竞品差距明显
- 56.2% 条目含 `<think>` 标签 (eval auto-strip, 不影响评估但数据不一致)

## 瓶颈分析

| 瓶颈 | 影响 | 解法 | 阶段 |
|------|------|------|------|
| 游戏覆盖缺口 | non-zero rate 被压低 (39%) | 补齐 4 个 Strong-tier 游戏 | v2 |
| SFT 天花板 | 极限 ~40-50 分 | DPO (589 对) 或 RL/MCTS | v3 |
| 无效数据占比 | 53.6% 训练预算浪费 | 降权 Zero-tier, 增权 learnable | v2 |
| leduc_poker 数据不足 | 47 条无法稳定学习 | 扩至 200+ | v2 |

## 数据行动方案

### v1: 用现有数据 (当前阶段 — 训练中)
- **不做修改**: 1,415 条全部用于 v1 baseline
- 目的: 建立 per-game 基线, 确认哪些游戏有效
- `game` 元数据字段已添加 (2026-03-18), 可做 per-game 分析
- 预期: GAME ~20-25 分 (基于 v11 历史)

### v2: 补齐游戏 + 优化 mix (Strategist 已下达指令)
| 任务 | 方法 | 预期条数 | 成本 | 优先级 |
|------|------|---------|------|--------|
| blackjack 数据生成 | `game_gen.py` (Tier 1, ~519 tok/条) | ~50 | 极低 | P1 |
| euchre 数据生成 | `game_gen.py` (Tier 1, ~5.8K tok/条) | ~50 | 低 | P1 |
| hearts 数据生成 | `game_gen.py` (Tier 2, ~27.5K tok/条) | ~50 | 中 | P2 |
| bridge 数据生成 | `game_gen.py` (Tier 4, ~50K tok/条) | ~50 | 高 | P3 (等 v1 结果) |
| leduc_poker 扩展 | bot 策略 | 47→200+ | 低 | P2 |
| Zero-tier 降权 | 训练时 downsample | — | 0 | P2 |

**生成方法**: `game_gen.py` 使用 qwen3-max + MCTS 对手, 非纯程序化 bot。
**输出到**: `data/canonical/game_v2_{game}.jsonl` (不修改 v1 文件)

### v3: DPO 突破
- 589 对偏好对已就绪
- 优先用于可学习但不稳定的游戏 (gin_rummy, leduc_poker)
- Zero-tier 游戏需要 RL/MCTS, SFT/DPO 都不够

## 投资策略 (游戏级别)

| 游戏 | 当前条数 | 当前胜率 | 行动 | 阶段 |
|------|---------|---------|------|------|
| goofspiel | 273 | 100% | 不投资 | — |
| gin_rummy | 430 | 100% | 维持 | — |
| leduc_poker | 47 | Strong | 扩到 200+ | v2 |
| hearts | 0 | — | **新建** (game_gen.py) | v2 |
| bridge | 0 | — | **新建** (等 v1 结果) | v2/v3 |
| blackjack | 0 | — | **新建** (Tier 1, 最便宜) | v2 |
| euchre | 0 | — | **新建** (Tier 1) | v2 |
| othello/hex/liars_dice/clobber | 665 | 0% | 不追加 SFT, 等 DPO/RL | v3+ |
| go/chess/checkers/solitaire | 0 | 0% | **永不投资** | — |

## 数据质量检查清单

- [x] `datasets.load_dataset('json', data_files=...)` 成功
- [x] Schema: `{"messages": [...], "env": "GAME", "score": float}`
- [x] 最后一条消息 role=assistant
- [x] System prompt 存在且包含游戏规则
- [x] Assistant 消息非空 (纯整数或 think+整数)
- [x] `game` 元数据字段已添加 (100% 覆盖)
- [ ] `task_id` 字段 (v2 补充)
- [ ] `source` 字段 (v2 补充)

## 准备文件

| 文件 | 位置 | 条数 | 状态 |
|------|------|------|------|
| canonical | `data/canonical/game.jsonl` | 1,415 | claudeuser-owned, v1 使用中 |
| v2 blackjack | `data/canonical/game_v2_blackjack.jsonl` | — | 待生成 |
| v2 euchre | `data/canonical/game_v2_euchre.jsonl` | — | 待生成 |
| v2 hearts | `data/canonical/game_v2_hearts.jsonl` | — | 待生成 |
| bot 策略脚本 | `scripts/game_gen.py` | — | 已支持全部 4 个新游戏 |
| DPO 数据 | — | 589 对 | 可用 (v3) |
