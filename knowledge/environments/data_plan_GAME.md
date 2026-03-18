# GAME 数据方案

> 最后更新: 2026-03-18 | 优先级: P1 (结构性天花板)

## 现状

| 指标 | 值 |
|------|-----|
| canonical 条数 | 1,415 |
| 分数 | 22.6 (v11), 39% non-zero |
| 榜首 | 63.2 (RLStepone) |
| GM 贡献潜力 | 22.6→35 = **+3.1 GM** |
| 数据格式 | multi-turn (system + user/assistant), assistant = think + action ID |
| 游戏覆盖 | 7/22+ 游戏 |

## 游戏分布 (审计结果)

| 游戏 | 条数 | 占比 | 可学性 |
|------|------|------|--------|
| gin_rummy | 430 | 30.4% | Bot-improved (0%→100%) |
| liars_dice | 327 | 23.1% | Zero (SFT 无效) |
| goofspiel | 273 | 19.3% | Solved (100%) |
| hex | 206 | 14.6% | Zero (SFT 无效) |
| clobber | 120 | 8.5% | Zero (SFT 无效) |
| leduc_poker | 47 | 3.3% | Strong |
| othello | 12 | 0.8% | Zero (SFT 无效) |

**严重问题**:
- 4 个 Strong-tier 游戏完全缺失: hearts, bridge, blackjack, euchre
- 53.6% 数据是 SFT 无法学习的游戏 (liars_dice + hex + clobber + othello)
- othello 仅 12 条 (0.8%)，严重不足
- 56.2% 条目含 `<think>` 标签 (eval 会 auto-strip，不是 blocker 但不一致)

## 瓶颈分析

1. **游戏覆盖缺口**: 缺失 4 个 Strong-tier 游戏 = non-zero rate 被压低
2. **SFT 天花板**: ~40-50 分，竞品 63.2 分用 RL
3. **无效数据占比高**: 53.6% 数据用于 SFT 无法学会的游戏
4. **缺少元数据**: 无 `game` 字段，无法做 per-game 分析

## 数据行动方案

### 短期 (v1: 用现有数据)
- **不做修改**: 1,415 条全部用于 v1 baseline
- 目的: 建立 per-game 基线，确认哪些游戏有效

### 中期 (v2: 补齐游戏 + 优化 mix)
- [ ] **编写 bot 策略**: hearts, bridge, blackjack, euchre (参考现有 game_bots.py)
- [ ] **添加 `game` 字段**: 从 system prompt 提取游戏类型
- [ ] **重新平衡 mix**: 降低 Zero-tier 游戏比例，增加 Strong/Bot-improved
- [ ] **扩展 leduc_poker**: 从 47→200+ (当前严重不足)
- [ ] 目标: 1,415 → 2,500+ 条，覆盖 11+ 可学游戏

### 长期 (v3: DPO)
- [ ] 589 对偏好对已就绪
- [ ] 优先用于可学习但不稳定的游戏
- [ ] Zero-tier 游戏需要 RL/MCTS，SFT/DPO 都不够

## 投资策略 (游戏级别)

| 游戏 | 当前 | 行动 | 预期 |
|------|------|------|------|
| goofspiel | 273, 100% 胜 | 不投资 | 维持 |
| gin_rummy | 430, 100% 胜 | 维持 | 维持 |
| leduc_poker | 47, Strong | 扩到 200+ | 提升 |
| hearts | 0 | **新建 bot** | 新增 |
| bridge | 0 | **新建 bot** | 新增 |
| blackjack | 0 | **新建 bot** | 新增 |
| euchre | 0 | **新建 bot** | 新增 |
| othello/hex/liars_dice/clobber | 665, 0% 胜 | 不追加 SFT | 等 DPO/RL |
| go/chess/checkers/solitaire | 0 | **永不投资** | — |

## 准备文件

| 文件 | 位置 | 条数 | 状态 |
|------|------|------|------|
| canonical | `data/canonical/game.jsonl` | 1,415 | root-owned, 待 chown |
| v1 用量 | 全量 | 1,415 | 直接使用 |
| bot 策略脚本 | `scripts/game_gen.py` | — | 需扩展 4 个新游戏 |
