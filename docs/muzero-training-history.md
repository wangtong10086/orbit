# MuZero 棋类游戏训练历史与分析

> 记录截至 2026-04-05，包括 Othello 8×8 和 Clobber 5×6 的全部训练轮次。
> 评估基线：`evaluate_vs_affine_mcts`，quick eval 200 局，双方各 64 次 MCTS 模拟。

---

## 目录

1. [系统架构](#系统架构)
2. [训练流程概述](#训练流程概述)
3. [硬件环境](#硬件环境)
4. [版本历史：Othello 8×8](#版本历史othello-8x8)
5. [版本历史：Clobber 5×6](#版本历史clobber-5x6)
6. [各版本横向对比](#各版本横向对比)
7. [已识别问题与模式](#已识别问题与模式)
8. [当前状态（v6）](#当前状态v6)
9. [待探索方向](#待探索方向)

---

## 系统架构

### 代码位置

```
projects/openspiel_muzero_pt/
  pipelines/
    train_online.py       — 在线训练主循环
    selfplay_actor.py     — 自对弈 actor 进程
    learner.py            — 损失计算与梯度更新
    warmstart.py          — 监督预热训练
    evaluate_vs_affine_mcts.py — 评估器（对战 MCTS 基线）
  runtime/
    gpu_coordinator.py    — GPU 时分复用（推理 + 训练）
    ring_buffer.py        — Replay buffer
    settings.py           — 配置解析
  configs/                — YAML 超参数配置
  games/
    adapters.py           — OpenSpiel 游戏适配器
```

### 单 GPU 时分架构

```
┌─────────────────────────────────────────┐
│               GPU Coordinator            │
│                                          │
│  ┌─────────────┐    ┌─────────────────┐ │
│  │ search_model│    │   train_model   │ │
│  │  (推理用)    │    │   (训练用)      │ │
│  └─────┬───────┘    └────────┬────────┘ │
│        │ 批量推理请求          │ 梯度更新  │
│        ▼                     ▼          │
│  ┌──────────────────────────────────┐   │
│  │         GPU 时间段轮转            │   │
│  │  推理帧 → 训练帧 → 推理帧 → ...   │   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
        ↑                       ↑
   Actor Workers             Replay Buffer
   (并行自对弈)               (live + expert)
```

关键：`snapshot_sync_interval` 控制 train_model → search_model 的权重同步频率。

### 损失函数

$$\mathcal{L} = \mathcal{L}_{\text{policy}} + \mathcal{L}_{\text{value}} + \mathcal{L}_{\text{reward}} + \lambda_{\text{KL}} \cdot \mathcal{L}_{\text{teacher-KL}}$$

- **policy loss**：交叉熵，预测 MCTS 搜索目标策略
- **value loss**：MSE，预测游戏最终结果
- **reward loss**：MSE，预测即时奖励（棋类游戏中通常近零）
- **teacher KL**（v5+）：$\text{KL}(\pi_{\text{teacher}} \| \pi_{\text{model}})$，专家数据上的策略锚定

---

## 训练流程概述

### 阶段 1：语料生成（Corpus）

从初始状态出发，用强力 MCTS（128 次模拟）标注棋局状态，生成 `state_corpus.jsonl`。

```
Othello: 4096 states  → state_corpus.jsonl (~569KB)
Clobber: 4096 states  → state_corpus.jsonl
```

### 阶段 2：专家数据生成（Expert）

对语料中每个状态运行高质量 MCTS 搜索，生成策略/价值标签，存储为 `.npz` 分片。

```
Othello v4: 128 expert shards
Clobber v4: 128 expert shards
```

### 阶段 3：预热训练（Warmstart）

在专家数据上进行监督学习（50k 步），将随机初始化的模型引导到合理的初始策略。

### 阶段 4：在线训练（Online）

自对弈 + 训练循环，目标步数 2,000,000。

Replay buffer 混合比例：
- `live`（自对弈数据）：50%
- `expert`（标注专家数据）：50%

---

## 硬件环境

| 参数 | 值 |
|------|-----|
| 机器 | `codex-muzero-train-h200x2` |
| GPU | 2× NVIDIA H200 (各 143 GB VRAM) |
| 主机 | 72.46.85.157:32526 |
| GPU 分配 | Othello → GPU 0，Clobber → GPU 1 |
| 训练框架 | PyTorch 2.6.0 + cu124，bf16 精度 |
| 算法 | Gumbel MuZero |

---

## 版本历史：Othello 8×8

### 模型结构（所有版本相同）

| 参数 | 值 |
|------|-----|
| channels | 128 |
| repr_blocks | 8 |
| dyn_blocks | 3 |
| head_hidden | 256 |
| unroll_steps | 3 |
| 参数量 | ~89 MB checkpoint |

---

### v4（2026-04-04，已结束）

**目标**：从头开始，探索使用更大模型和更多专家数据能否取得收敛。

**关键超参数**

| 参数 | 值 |
|------|-----|
| `lr_online` | 1.0e-4 |
| `batch_size_per_gpu` | 128 |
| `snapshot_sync_interval` | 100 |
| `expert_min_ratio` | 0.1（允许专家数据衰减至 10%）|
| `expert_decay_steps` | 0（不衰减）|
| `actors.workers` | 12 |
| `live_capacity` | 300,000 |

**预热结果**

- 50k 步监督训练
- 预热结束 WR：**29%**（vs MCTS 64 sim baseline）

**在线训练 WR 历史**

| eval # | Step | WR |
|--------|------|----|
| 1 | 10,000 | 0.340 |
| 2 | 60,000 | 0.200 |
| 3 | 110,000 | 0.240 |
| 4 | 160,000 | 0.355 |
| 5 | 210,000 | 0.355 |
| 6 | 260,000 | 0.370 |
| 7 | 310,000 | **0.400** |

**最终状态**：step ~350k，loss 2.5，最高 WR **40%**（step 310k）。在 v5 启动前手动终止。

**损失轨迹（每 50k 步采样）**

| Step | Loss |
|------|------|
| 200 | 3.190 |
| 50k | 2.615 |
| 100k | 2.475 |
| 150k | 2.429 |
| 200k | 2.590 |
| 250k | 2.529 |
| 300k | 2.518 |
| 350k | 2.521 |

**诊断**：loss 在 2.43-2.60 停滞，未继续下降。WR 波动较大（0.20-0.40），表明学习不稳定。

---

### v5（2026-04-04 至 04-05，已结束）

**目标**：在 v4 基础上增加三大改进：
1. **Gated snapshot**：仅在 eval WR 提升时才将 train_model → search_model（防止非稳态自对弈污染）
2. **持续教师 KL 锚定**：每步在专家数据上额外计算 KL(teacher‖model)，weight=0.5
3. **降低 update/data ratio**：LR 减半（1e-4 → 5e-5），snapshot 同步间距拉大（100 → 500）

**起点**：v4 warmstart checkpoint（WR 29%）

**关键超参数变化（相比 v4）**

| 参数 | v4 | v5（修改） | 原因 |
|------|----|----|------|
| `lr_online` | 1.0e-4 | **5.0e-5** | 减少每步 SGD 更新幅度 |
| `snapshot_sync_interval` | 100 | **500** | 降低更新频率避免振荡 |
| `gated_snapshot` | 无 | **true** | 只在 WR 改善时刷新 search_model |
| `teacher_kl_weight` | 无 | **0.5** | 持续 KL 锚定，防止偏离教师策略 |
| `expert_min_ratio` | 0.1 | **0.5** | 教师数据比例永久保持 50% |

**在线训练 WR 历史**

| eval # | Step | WR | 备注 |
|--------|------|----|----|
| 1 | 10,000 | 0.370 | ✓ gated 触发 |
| 2 | 50,000 | 0.395 | ✓ gated 触发 |
| 3 | 90,000 | 0.335 | — |
| 4 | 130,000 | 0.360 | — |
| **5** | **170,000** | **0.460** | **✓ gated 触发，全局最高** |
| 6 | 210,000 | 0.365 | — |
| 7–22 | 250k–850k | 0.265–0.400 | gated 未再触发 |

**search_model 冻结点**：step 170,000（WR 0.46）

**平台期诊断**（step 170k → 916k，持续 **750k 步**）

- search_model 在 WR=0.46 时被 gated snapshot 永久锁定
- 所有自对弈数据均来自同一固定策略
- train_model 在固定分布上循环过拟合，eval WR 无法超越 0.46
- teacher_kl 从 0.023（step 2k）降至 0.005（step 900k）—— 模型已收敛到教师策略，但无新的自对弈探索

**损失轨迹（每 50k 步采样）**

| Step | Loss | teacher_kl |
|------|------|------------|
| 200 | 3.068 | 0.0177 |
| 50k | 2.628 | 0.0028 |
| 100k | 2.557 | 0.0026 |
| 200k | 2.509 | 0.0053 |
| 400k | 2.497 | 0.0033 |
| 600k | 2.594 | 0.0042 |
| 900k | 2.554 | 0.0062 |

**结论**：v5 在 step 170k 取得最高 WR 0.46，随后因 gated snapshot 死锁进入无法突破的平台。

---

### v6（2026-04-05，进行中）

**目标**：从 v5 Best checkpoint（WR 0.46）出发，禁用 gated_snapshot，允许 search_model 自由更新，打破平台期锁死。

**起点**：v5 online best.pt（step 170k，WR 0.46）

**关键超参数变化（相比 v5）**

| 参数 | v5 | v6（修改） |
|------|----|----|
| `gated_snapshot` | true | **false** |
| 其余参数 | — | 同 v5 |

**在线训练 WR 历史（至 2026-04-05 08:24）**

| eval # | Step | WR |
|--------|------|----|
| 1 | 10,000 | 0.260 |
| 2 | 50,000 | 0.320 |

**当前状态**：step 102,800，best_WR **0.32**

**初期 loss 轨迹**

| Step | Loss | teacher_kl |
|------|------|------------|
| 200 | 3.235 | 0.0034 |
| 10k | 2.293 | 0.0062 |
| 20k | 2.283 | 0.0056 |
| 50k | 2.507 | 0.0053 |
| 90k | 2.426 | 0.0035 |

**初期 WR 下降解释**：v6 从 WR 0.46 的最优 checkpoint 出发，但 replay buffer 从空开始重建，早期大量随机/低质量游戏稀释了数据，WR 短暂回落到 0.26-0.32 属于正常"热身"现象。需等到 ~200k 步才能判断是否能突破 0.46。

---

## 版本历史：Clobber 5×6

### 模型结构（所有版本相同）

| 参数 | 值 |
|------|-----|
| channels | 128 |
| repr_blocks | 10 |
| dyn_blocks | 4 |
| head_hidden | 256 |
| unroll_steps | 3 |
| 参数量 | ~91 MB checkpoint |

---

### v4（2026-04-04，已结束）

**预热结果**：50k 步，WR **25%**

**在线训练 WR 历史（前 35 次 eval）**

| eval # | Step | WR |
|--------|------|----|
| 1 | 10,000 | 0.175 |
| 5 | 50,000 | 0.160 |
| 10 | 100,000 | 0.170 |
| 14 | 140,000 | **0.235** |
| 19 | 190,000 | 0.235 |
| 20 | 200,000 | 0.195 |
| 29 | 290,000 | 0.235 |
| 35 | 350,000 | 0.175 |

**结论**：WR 始终在 0.12-0.24 震荡，无稳定上升趋势。最高 WR 约 0.235。

---

### v5（2026-04-04 至 04-05，已结束）

**起点**：v4 warmstart checkpoint（WR 25%）

**配置**：与 Othello v5 相同设计，gated_snapshot=true，teacher_kl_weight=0.5。

**在线训练 WR 历史（关键节点）**

| eval # | Step | WR | 备注 |
|--------|------|----|----|
| 1 | 10,000 | 0.120 | ✓ gated |
| 2 | 20,000 | 0.165 | ✓ gated |
| 3 | 30,000 | 0.205 | ✓ gated |
| 4 | 40,000 | 0.210 | ✓ gated |
| 20 | 200,000 | 0.215 | ✓ gated |
| 34 | 340,000 | 0.215 | ✓ gated（相等值触发）|
| **43** | **430,000** | **0.245** | **✓ gated，全局最高** |
| 44–81 | 440k–810k | 0.100–0.215 | gated 未再触发 |

**search_model 冻结点**：step 430,000（WR 0.245）

**平台期诊断**（step 430k → 808k，持续 **378k 步**）

同 Othello v5：gated snapshot 在 step 430k 后锁定 search_model，自对弈数据分布停止进化。

**teacher_kl 轨迹**

| Step | teacher_kl |
|------|------------|
| 100 | 0.0464 |
| 50k | 0.0487 |
| 200k | 0.0353 |
| 500k | 0.0326 |
| 800k | 0.0418 |

Clobber 的 teacher_kl 比 Othello 高 10 倍（0.04 vs 0.004），说明 Clobber 模型到训练后期仍未完全消化教师策略，与教师的策略偏差更大。

**结论**：v5 Clobber 收敛到 WR 24.5%，远低于预热基线（WR 25%），可能表明 WR 和对手强度的相对关系存在波动，也可能表明 Clobber 5×6 本身比 Othello 更难学（状态空间不同、游戏长度短但策略深度高）。

---

### v6（2026-04-05，进行中）

**起点**：v5 online best.pt（step 430k，WR 0.245）

**配置**：gated_snapshot=false，其余同 v5。

**在线训练 WR 历史（至 2026-04-05 08:24）**

| eval # | Step | WR |
|--------|------|----|
| 1 | 10,000 | 0.185 |
| 2 | 20,000 | 0.135 |
| 3 | 30,000 | 0.170 |
| 4 | 40,000 | 0.165 |
| 5 | 50,000 | 0.150 |
| 6 | 60,000 | 0.155 |
| 7 | 70,000 | 0.180 |
| 8 | 80,000 | 0.190 |

**当前状态**：step 91,700，best_WR **0.19**

**初期 loss 轨迹**

| Step | Loss | teacher_kl |
|------|------|------------|
| 100 | 3.445 | 0.0464 |
| 10k | 2.113 | 0.0585 |
| 30k | 2.285 | 0.0332 |
| 60k | 2.719 | 0.0278 |
| 80k | 2.637 | 0.0505 |

---

## 各版本横向对比

### Othello 8×8

| 版本 | 起点 WR | 最高 WR | 达到最高时 step | gated | teacher_kl | LR |
|------|---------|---------|--------------|-------|------------|-----|
| v4 | 29%（warmstart）| **40%** | 310k | ✗ | ✗ | 1e-4 |
| v5 | 29%（warmstart）| **46%** | 170k | ✓（后来成为瓶颈）| 0.5 | 5e-5 |
| v6 | 46%（v5 best）| **32%**（当前）| 进行中 | ✗ | 0.5 | 5e-5 |

### Clobber 5×6

| 版本 | 起点 WR | 最高 WR | 达到最高时 step | gated | teacher_kl | LR |
|------|---------|---------|--------------|-------|------------|-----|
| v4 | 25%（warmstart）| ~23.5% | ~190k | ✗ | ✗ | 1e-4 |
| v5 | 25%（warmstart）| **24.5%** | 430k | ✓（后来成为瓶颈）| 0.5 | 5e-5 |
| v6 | 24.5%（v5 best）| **19%**（当前）| 进行中 | ✗ | 0.5 | 5e-5 |

---

## 已识别问题与模式

### 问题 1：Gated Snapshot 死锁

**现象**：v5 中两个游戏均在达到某个 WR 峰值后，gated snapshot 将 search_model 永久冻结，训练陷入无法突破的平台。

**机制分析**：
```
search_model 冻结在 best WR
    ↓
自对弈数据分布 = 固定策略 D_frozen
    ↓
train_model 在 D_frozen 上过拟合
    ↓
新 policy = old policy 的微小变体（未探索新棋局）
    ↓
eval WR ≤ best WR → gated 不触发 → 继续循环
```

**结论**：gated snapshot 适合短期稳定，不适合长期持续改进。在策略已达到局部最优时，需要允许更多探索，而不是锁死。

---

### 问题 2：WR 评估方差过大

**现象**：连续多次 eval 的 WR 波动范围 ±0.1，例如 Clobber v5：

```
Step 60k: 0.205
Step 70k: 0.150  （-0.055，-26%）
Step 80k: 0.195
Step 90k: 0.140
```

**原因**：quick eval 只有 200 局，WR 的标准误差约为 $\sqrt{0.2 \times 0.8 / 200} \approx 0.028$（±2.8%），但波动实测达到 ±8%，超出统计范围，可能因搜索树随机性叠加导致。

**影响**：gated snapshot 用单次 eval 的 WR 决定是否更新模型。由于方差大，一次异常高的 WR 会导致过早锁定，一次异常低的 WR 会阻止合理更新。

---

### 问题 3：Clobber 学习效率显著低于 Othello

**数据对比**：

| 指标 | Othello v5 | Clobber v5 |
|------|-----------|------------|
| 最高 WR | 46% | 24.5% |
| 到达最高 WR 的 step | 170k | 430k |
| teacher_kl @ 最高 WR | ~0.007 | ~0.05 |
| teacher_kl @ 训练末尾 | 0.003-0.005 | 0.03-0.05 |

Clobber 的 teacher_kl 持续高于 Othello 10 倍，说明 Clobber 5×6 棋局中模型更难拟合 MCTS 策略。可能原因：
- Clobber 的胜负判断规则更复杂（最后无法移动者输），策略不连续
- Clobber 的专家数据量（128 shards）可能不足以覆盖多样策略
- Clobber 的平均游戏长度仅 17 步，但战略深度高，策略空间离散

---

### 问题 4：Loss 不再下降≠训练停止收益

**现象**：从 step 50k 开始，两个游戏的 loss 均稳定在 2.3-2.7，不再明显下降，但 WR 仍有微小波动。

**解释**：MuZero 的 loss 包含 policy/value/reward 三项，policy loss 本质上是与 MCTS 搜索目标的交叉熵，而 MCTS 搜索目标本身会随策略提升而改变（reanalyse），导致 loss 底部存在"移动目标"效应。

---

### 问题 5：从最优 checkpoint 重启导致 WR 暂时下降

**现象**：v6 两个游戏均从 v5 最优 checkpoint 出发，初期 WR 均明显低于出发点：
- Othello：出发 46% → v6 step 10k 时 26%
- Clobber：出发 24.5% → v6 step 10k 时 18.5%

**解释**：replay buffer 从零开始重建，早期含大量低质量游戏（模型与自身弱拷贝对局），分布与 eval 时不同，导致 WR 偏低。这是预期行为，通常在 buffer 填充后（~100-200k steps）才能回升至出发点水平。

---

## 当前状态（v6）

截至 2026-04-05 08:24（UTC）

| | Othello v6 | Clobber v6 |
|--|-----------|-----------|
| 当前 step | 102,800 | 91,700 |
| 进度 | 5.1% | 4.6% |
| 当前 loss | 2.69 | 2.58 |
| teacher_kl | 0.0044 | 0.0656 |
| best WR | **0.32** | **0.19** |
| 上次 eval WR | 0.32 | 0.19 |
| 训练开始时间 | 2026-04-05 06:52 UTC | 2026-04-05 06:52 UTC |

---

## 待探索方向

以下方向均未在当前训练循环中尝试，可能对突破现有瓶颈有帮助：

### 方向 A：修复 Gated Snapshot 的使用方式

问题：单次 eval（200 局）方差太大，不适合作为门控依据。

建议改进：
- 用滑动平均 WR（3-5 次 eval 均值）代替单次 WR 作为门控依据
- 或者，仅在滑动均值超过历史最高值的一定阈值（如 +2%）时才触发 gate
- 或者，对 gated snapshot 增加一个"强制解冻"计时器：如果超过 N 步没有触发，强制同步

### 方向 B：混合对手池（Fictitious Self-Play / PFSP）

当前：所有 actor 共享同一个 search_model，对手永远是"自己"。

建议：维护一个历史 checkpoint 池，actor 以一定概率选择对手：
- 50%：当前策略 vs 当前策略（标准自对弈）
- 30%：当前策略 vs 历史 checkpoint（历史 k 个中随机选）
- 20%：当前策略 vs 教师 MCTS（产生高质量数据）

这是 AlphaStar / OpenAI Five 的核心技巧，有助于防止策略循环（A 赢过 B，B 赢过 C，C 赢过 A）。

### 方向 C：增加专家数据量与多样性

当前：4096 状态，128 shards，由相对简单的初始分布生成。

建议：
- 增加专家状态数量至 16k-64k（覆盖更多中局、残局状态）
- 加入基于当前在线策略产生的状态（边训练边补充专家库）
- 对 Clobber 专项增加中局战术位置（当前专家可能集中在初始开局）

### 方向 D：调整 Replay Buffer 组合

当前配置：replay_ratio = {live: 0.5, expert: 0.5}，live_capacity = 300,000

观察：Clobber teacher_kl 始终高，说明模型对专家数据整体拟合不够充分。

建议：
- 训练早期（step < 100k）：提高 expert 比例至 0.7，压低 live 至 0.3
- 训练中期（100k-500k）：逐步切换至 {live: 0.6, expert: 0.4}
- 这样避免早期被低质量自对弈数据稀释专家信号

### 方向 E：Reanalyse（后验搜索再标注）

当前代码已有 `reanalyse_num_simulations: 64` 配置，但观察事件日志未见 reanalyse 被触发。

Reanalyse 是 MuZero 原论文的关键组件：对 replay buffer 中的旧数据用当前模型重新跑 MCTS，刷新策略/价值标签。这可以让旧游戏数据持续提供有效监督信号，防止数据"变陈旧"。

建议验证：
1. 确认 `reanalyse` 是否实际运行（检查事件日志中是否有 reanalyse 相关 kind）
2. 如未运行，调查原因并启用

### 方向 F：更强的 MCTS 搜索（训练时）

当前：`train_num_simulations: 64`

建议测试：将训练时 MCTS 模拟次数提升至 128-256，生成质量更高的自对弈数据。代价是吞吐量下降约 50%，但数据质量提升可能弥补。对 Clobber 尤其值得尝试（当前数据质量不足可能是核心瓶颈）。

### 方向 G：Clobber 专项调试

Clobber 的 WR 上限（~25%）远低于 Othello（~46%），且 teacher_kl 持续偏高，表明 Clobber 模型学习困难。

建议：
1. 运行一次诊断评估：比较 `model MCTS(64sim)` vs `model MCTS(256sim)` 的 WR，判断是否只是搜索深度不够
2. 可视化模型在几个典型 Clobber 局面的策略概率分布，与 MCTS 目标对比
3. 考虑减小模型（repr_blocks 10 → 6，channels 128 → 96），降低参数量，加快拟合速度

---

*文档最后更新：2026-04-05，基于 v6 step ~95k 数据*
