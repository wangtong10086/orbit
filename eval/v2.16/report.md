# v2.16 实验报告

## 实验概述

- **目标**: GAME v12 system prompt 修复（think-then-act 替代 suppress-thinking）+ 全量数据训练
- **假设**: v12 think 指令解锁推理能力，spatial games (othello/hex/clobber) 可能开始得分，NW/LW 通过推理能力提升受益
- **数据**: GAME 6511 (70%) + NW 1700 (18%) + LW 1055 (11%) = 9266。全部 canonical，不做 subsample
- **训练**: lr=5e-5, epochs=1, LoRA r=64, seq=8192, 4×H200 DDP, 322 steps, loss 0.204
- **评测**: temperature=0, AMAP keys ✅, LIVEWEB cache 部分覆盖, 100 samples/env

## 评测结果汇总

| Env | v2.7 | v2.13b (prev best) | **v2.16** | vs v2.13b |
|-----|------|---------------------|-----------|-----------|
| GAME | 28.90 | 28.12 | **26.75** | -4.9% |
| **NAVWORLD** | 12.63 | 25.13 | **35.46** | **+41.1%** |
| LIVEWEB | 13.76 | 11.03 | **6.49** | -41.2% |

## GAME 详细分析

### Per-game breakdown

| Game | N | 非零率 | 平均分 | 最高分 | 状态 |
|------|---|--------|--------|--------|------|
| goofspiel | 15 | 87% (13/15) | 86.7 | 1.00 | ✅ 强 |
| leduc_poker | 14 | 100% (14/14) | 50.8 | 0.77 | ✅ 强 |
| gin_rummy | 14 | 100% (14/14) | 47.4 | 0.69 | ✅ 强 |
| liars_dice | 15 | 0% (0/15) | 0.0 | 0.00 | ❌ 零分 |
| hex | 14 | 0% (0/14) | 0.0 | 0.00 | ❌ 零分 |
| othello | 14 | 0% (0/14) | 0.0 | 0.00 | ❌ 零分 |
| clobber | 14 | 0% (0/14) | 0.0 | 0.00 | ❌ 零分 |

### vs v2.13b 对比

v2.13b per-game: goofspiel 86.7, leduc 54.1, gin_rummy 46.9, liars_dice 6.7, hex 0, othello 0, clobber 0.

- **v12 think prompt 没有解锁 spatial games** — hex/othello/clobber 仍然 0%
- **liars_dice 从 6.7% 退回 0%** — v12 的 think 模式反而影响了 bluffing
- goofspiel/leduc/gin_rummy 基本持平

### 零分游戏根因

4/7 games 零分，且 v12 think-then-act 未改善：
- **SFT 无法教会位置推理**：hex/othello 需要 board state evaluation，think chain 中只是文字推理，无法替代真正的搜索/评估
- **clobber 需要全局视野**：模型的 think 可能在推理但推理方向错误
- **liars_dice 退步**：think 模式让模型 "想太多"，bluffing 需要快速决策

**结论：GAME SFT ceiling 仍为 ~27-28。spatial games 需要 GRPO/RL，不是更好的 prompt。**

## NAVWORLD 详细分析

### 核心数据

- **得分率 96%** (96/100 non-zero) — 历史最高
- **平均分 35.46** — v2.13b 的 1.41 倍
- ≥0.5: 27 tasks, ≥0.75: 5 tasks
- 0 errors, AMAP keys 正常

### 为什么 NW 大幅提升 (+41% vs v2.13b)

v2.16 与 v2.13b 的唯一核心区别是 GAME v12 system prompt（think-then-act）。NW 数据本身基本没变（1660→1700）。

**理论：GAME v12 的 think 训练产生了 cross-training 效果，模型学会了在所有任务中 "先思考再行动"，这对 NW 的多步工具调用推理（路线规划、POI 搜索、天气查询）极为有益。**

NW 任务需要：先理解任务目标 → 规划工具调用顺序 → 执行并验证。v12 的 think 训练恰好强化了这个 "规划-执行" 链。

### 零分样本 (4/100)

仅 4 个零分任务（vs v2.13b 的 31 个），说明模型几乎能处理所有 NW 任务类型。

## LIVEWEB 详细分析

### 核心数据

- Scoring: 18/100 (18%), Zero: 70/100 (70%), Errors: 12/100 (12%)
- Max score: 0.50 — 没有满分任务
- 12 errors 全部是 cache 问题（Stooq API limit, HTTP 404）

### 根因：GAME think pattern 导致导航循环

通过对比同一 task_id 在 v2.13b 和 v2.16 的表现：

| 指标 | v2.13b | v2.16 | 变化 |
|------|--------|-------|------|
| action_failed | 36 | 154 | +4.3x |
| repeated_url | 186 | 291 | +1.6x |
| no_progress | 213 | 321 | +1.5x |

**具体案例**: Task 80801587 — v2.13b 用 7 条消息得 0.12 分，v2.16 用 172 条消息得 0 分。v2.16 模型对同一个 URL 执行了 57 次 `goto` 操作。

**根因**: GAME v12 训练模型 "坚持同一动作直到成功"（对棋盘游戏合理），但在浏览器导航中变成死循环。模型缺乏 "失败后换策略" 的训练信号。

### 改进方向

1. **失败恢复训练数据**: URL 404 → 搜索替代 → 找到数据
2. **策略切换示例**: 方法 A 失败 → 方法 B 成功
3. **不能通过增加相同类型的 LW 数据解决** — 需要专门的 adversarial/recovery 训练数据

## 根因分析总结

| 环境 | 不得分根因 | 分类 |
|------|-----------|------|
| GAME (4/7 games 0%) | SFT 无法教位置推理 | 模型能力 (需要 GRPO) |
| GAME (liars_dice 退步) | think 模式影响 bluffing | 训练配置副作用 |
| NAVWORLD (仅 4/100 零分) | 极少数复杂导航任务 | 数据质量 (已很好) |
| LIVEWEB (70% 零分) | GAME think 模式导致导航循环 | 数据质量 (需要 recovery 数据) |
| LIVEWEB (12% error) | Cache 覆盖不全 | eval 基础设施 |

## 下一步建议

1. **GAME**: SFT ceiling 确认 ~27。hex/othello/clobber 必须用 GRPO/RL。不要再投入 SFT 数据。
2. **NAVWORLD**: v2.16 已达 35.46，继续优化 NW 数据但 ROI 递减。保持现有数据质量。
3. **LIVEWEB**:
   - 需要 50-100 条 "导航失败→换方法→成功" 的 adversarial 训练数据
   - 需要覆盖 stooq/coingecko/taostats 三个站点的恢复模式
   - 更新 eval cache 消除 12% 的基础设施错误
4. **部署决策**: v2.16 (NW 35.46) vs v2.13b (balanced) 取决于 leaderboard scoring 中 NW 权重
