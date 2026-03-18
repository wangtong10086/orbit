# GAME 数据方案

> 最后更新: 2026-03-18 | 优先级: P1 (结构性天花板) | v1 状态: 训练中

## 现状

| 指标 | 值 |
|------|-----|
| canonical 条数 | **2,416** (恢复 + bot 策略数据) |
| v1 用量 | 1,415 (v1 训练用的旧数据) |
| v2 可用 | 2,269 |
| v3 可用 | 2,416 (+147 gin_rummy bot) |
| 历史分数 | 22.6 (v11), 39% non-zero |
| 竞品最高 | 50.75 (affshoot) |
| GM 贡献潜力 | 22.6→40 = **+4.5 GM** |
| 数据格式 | multi-turn (system + user/assistant), assistant = think + action ID |
| eval 活跃游戏 | **7 个** (goofspiel, liars_dice, leduc_poker, gin_rummy, othello, hex, clobber) |
| eval task_id 范围 | `[[0,500M],[600M,800M]]` (排除 backgammon idx=5, 及 idx≥8) |

## 评估格式详解 (源码: repos/affinetes)

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
- 300 样本评估 (scheduling_weight=3.0), timeout=7200s, concurrency=4

### Task ID 结构
- 格式: `game_idx * 100_000_000 + config_id`
- 例: game_idx=2 (leduc_poker), config=12345 → task_id=200012345
- **活跃 game_idx**: [0,1,2,3,4,6,7] (不含 5=backgammon, 不含 8+)

### Eval 参数
- Temperature: 0.7
- Memory: 2GB
- Docker image: openspiel:eval
- `--concurrency 4 --timeout 7200` (旧 600s timeout 会漏掉长游戏)

## 游戏分布 (2269 条, 仅活跃游戏)

| 游戏 | 条数 | 占比 | 可学性 | game_idx |
|------|------|------|--------|----------|
| goofspiel | 921 | 38.1% | Solved (100%) | 0 |
| gin_rummy | 505 | 20.9% | Bot-improved (0%→100%) | 3 |
| liars_dice | 333 | 13.8% | Zero (SFT 无效) | 1 |
| leduc_poker | 332 | 13.7% | Strong | 2 |
| hex | 190 | 7.9% | Zero (SFT 无效) | 6 |
| clobber | 123 | 5.1% | Zero (SFT 无效) | 7 |
| othello | 12 | 0.5% | Zero (SFT 无效) | 4 |

**可学性分布 (v3 bot 数据后)**:

| 可学性 Tier | 条数 | 占比 |
|------------|------|------|
| Solved (goofspiel) | 921 | 38.1% |
| Strong (leduc_poker) | 332 | 13.7% |
| Bot-improved (gin_rummy) | 505 | 20.9% |
| **Zero / SFT-unlearnable** | **658** | **27.2%** |

- **可学数据**: 1758 条 (72.8%) — bot 数据后持续改善
- **不可学数据**: 658 条 (29%) — 建议降采样
- **v2 建议**: 降采样 Zero-tier 从 658→~200 (每游戏 50)

## 瓶颈分析

| 瓶颈 | 影响 | 解法 | 阶段 |
|------|------|------|------|
| SFT 天花板 | 极限 ~40-50 分 | DPO (589 对) 或 RL/MCTS | v3 |
| Zero-tier 占比 | 29% 训练预算浪费 | 降采样到 ~200 条 | v2 |
| 数据来源单一 | 缺少 bot 策略数据 | game_bot_gen.py 重新生成 | v2 |

**注意**: hearts/bridge/blackjack/euchre 不在 eval task_id 范围内 (idx≥8), 无需投入。

## 数据行动方案

### v1: 用现有数据 (当前阶段 — 训练中)
- v1 用 1,415 条旧数据训练
- 目的: 建立 per-game 基线, 确认哪些游戏有效
- 预期: GAME ~20-25 分 (基于 v11 历史)

### v2: 优化 mix (恢复后数据 + 降采样)
| 任务 | 方法 | 目标 | 优先级 |
|------|------|------|--------|
| 使用恢复的 2269 条 | 已完成 | 直接用于 v2 训练 | ✅ |
| Zero-tier 降采样 | 训练时 downsample 658→~200 | 释放 ~460 条预算 | P1 |
| bot 策略数据 gin_rummy | `game_bot_gen.py` 200 条 → 147 新增 | ✅ 已完成 | ✅ |
| bot 策略数据 leduc_poker | `game_bot_gen.py` 200 条 → 0 新增 (fingerprint 去重) | 需改去重策略 | P2 |

**Bot 生成经验 (2026-03-18)**:
- `OPENSPIEL_DIR=repos/affinetes/environments/openspiel` 可用
- gin_rummy: 97% 胜率, 高质量。leduc_poker: 63% 胜率, 但短对话导致 fingerprint 碰撞严重
- 当前 fingerprint 去重 (前 3 条消息 × 前 200 chars) 对短游戏过于激进
- 建议: leduc_poker 改用全消息 hash 或加 seed 字段去重

**生成工具**: `scripts/game_bot_gen.py` (程序化 bot) + `scripts/game_gen.py` (LLM distillation)
**依赖**: 两者都需要 `repos/affinetes/environments/openspiel/` + `pyspiel`

### v3: DPO 突破
- 589 对偏好对已就绪
- 优先用于可学习但不稳定的游戏 (gin_rummy, leduc_poker)
- Zero-tier 游戏需要 RL/MCTS, SFT/DPO 都不够

## 投资策略 (仅限 7 个活跃游戏)

| 游戏 | 条数 | 胜率 | 行动 | 阶段 |
|------|------|------|------|------|
| goofspiel | 921 | 100% | 不追加 | — |
| gin_rummy | 358 | 100% | 维持 | — |
| leduc_poker | 332 | Strong | 维持 (恢复后已充足) | — |
| liars_dice | 333 | 0% | 降采样到 ~50 | v2 |
| hex | 190 | 0% | 降采样到 ~50 | v2 |
| clobber | 123 | 0% | 降采样到 ~50 | v2 |
| othello | 12 | 0% | 降采样到 ~12 (已经很少) | v2 |

**不在 eval 范围的游戏 (不投资)**: hearts, bridge, blackjack, euchre, backgammon, go, chess, checkers, dots_and_boxes, quoridor, phantom_ttt, 2048, solitaire, amazons, oware

## 数据质量检查清单

- [x] `datasets.load_dataset('json', data_files=...)` 成功
- [x] Schema: `{"messages": [...], "env": "GAME", "score": float}`
- [x] 最后一条消息 role=assistant
- [x] System prompt 存在且包含游戏规则
- [x] Assistant 消息非空 (纯整数或 think+整数)
- [x] `game` 元数据字段 (100% 覆盖)
- [x] 仅包含 7 个活跃游戏 (已过滤)
- [x] 与 canonical 去重 (fingerprint)
- [x] HF 已同步

## 准备文件

| 文件 | 位置 | 条数 | 状态 |
|------|------|------|------|
| canonical | `data/canonical/game.jsonl` | 2,269 | claudeuser-owned, HF 已同步 |
| bot 策略脚本 | `scripts/game_bot_gen.py` | — | 支持 7 个游戏的 bot |
| LLM 蒸馏脚本 | `scripts/game_gen.py` | — | 需 pyspiel + affinetes |
| DPO 数据 | — | 589 对 | 可用 (v3) |
| eval 源码 | `repos/affinetes/environments/openspiel/` | — | 只读参考 |
| 系统配置 | `repos/affine-cortex/affine/database/system_config.json` | — | task_id 范围定义 |
