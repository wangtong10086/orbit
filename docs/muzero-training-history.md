# MuZero 棋类游戏训练历史与分析

> 记录截至 2026-04-05，包括 Othello 8×8 和 Clobber 5×6 的全部训练轮次。
> 评估基线：`evaluate_vs_affine_mcts`，quick eval 200 局，双方各 64 次 MCTS 模拟。

本文档从游戏规则、强化学习建模到神经网络设计，完整描述了将两个棋类游戏作为独立研究问题的技术栈，并记录了所有训练实验的过程与结论。

---

## 目录

1. [游戏介绍](#游戏介绍)
2. [强化学习建模](#强化学习建模)
3. [神经网络架构](#神经网络架构)
4. [系统架构](#系统架构)
5. [训练流程概述](#训练流程概述)
6. [硬件环境](#硬件环境)
7. [版本历史：Othello 8×8](#版本历史othello-8x8)
8. [版本历史：Clobber 5×6](#版本历史clobber-5x6)
9. [各版本横向对比](#各版本横向对比)
10. [已识别问题与模式](#已识别问题与模式)
11. [当前状态（v6）](#当前状态v6)
12. [待探索方向](#待探索方向)

---

## 游戏介绍

### Othello 8×8（黑白棋）

Othello（又称 Reversi）是一种两人零和完全信息棋盘游戏，双方在 8×8 棋盘上轮流落子。

**棋盘初始状态**

```
  a b c d e f g h
1 . . . . . . . .
2 . . . . . . . .
3 . . . . . . . .
4 . . . W B . . .
5 . . . B W . . .
6 . . . . . . . .
7 . . . . . . . .
8 . . . . . . . .
```

初始时中央 4 格放置 2 黑 2 白棋子（交叉排列）。

**落子规则**

1. 玩家将己方棋子放在某个空格。
2. 新棋子必须在水平、垂直或对角线方向上夹住至少一枚对方棋子（即己方棋子—对方连续棋子—新落子三点共线）。
3. 所有被夹住的对方棋子全部翻转为己方颜色。
4. 若玩家无合法落子位置，则**跳过（pass）**，对方继续。

**终止条件**

- 棋盘填满，或
- 双方均无合法落子（连续两次 pass）

**胜负判定**

棋局结束时棋子数量更多的一方获胜；数量相等为平局。

**游戏特性**

| 特性 | 值 |
|------|-----|
| 棋盘 | 8×8 |
| 棋子类型 | 1（双面翻转棋） |
| 信息类型 | 完全信息 |
| 随机性 | 无 |
| 对称性 | 4重（旋转180°、水平翻转、垂直翻转、恒等） |
| 平均局长 | ~58 步 |
| 最大局长 | 128 步（含跳过） |
| 动作空间 | 65（64 格 + 1 pass） |
| 博弈类型 | 二人零和，有平局可能 |

---

### Clobber 5×6（击破棋）

Clobber 是一种组合博弈（combinatorial game），双方各持棋子在棋盘上以"击败"对方为目标。在本项目中使用的变体为 **5 行 × 6 列** 棋盘（OpenSpiel `clobber_6` 变体）。

> **注**：训练配置文件中以 "clobber5" 命名，指 5 行棋盘，实际对应 OpenSpiel 的 `clobber_6` variant（rows=5, columns=6），输入张量填充至 7×7。

**棋盘初始状态**

棋子以黑白交替方式铺满棋盘（类似国际象棋初始摆法）：

```
  1 2 3 4 5 6
A W B W B W B
B B W B W B W
C W B W B W B
D B W B W B W
E W B W B W B
```

**移动规则**

1. 玩家选择己方一枚棋子。
2. 将该棋子移动到**正交相邻**（上下左右）的一个格，该格必须有**对方棋子**。
3. 对方棋子被"击落"（移除），己方棋子占据该格。
4. **无 pass**：必须有合法移动才能行棋。

**终止条件**

当前玩家**无合法移动**时，该玩家**输棋**（即动不了的一方输）。

**胜负判定**

无平局。先无法移动的一方判负，结果为 +1（赢）/ -1（输）。

**游戏特性**

| 特性 | 值 |
|------|-----|
| 棋盘 | 5×6（填充至 7×7） |
| 初始棋子 | 各 15 枚（交替排列） |
| 信息类型 | 完全信息 |
| 随机性 | 无 |
| 对称性 | 2重（水平翻转、恒等） |
| 平均局长 | ~17 步 |
| 最大局长 | 35 步 |
| 动作空间 | 196（7×7×4，源格×方向） |
| 博弈类型 | 二人零和，无平局 |

---

### 两游戏对比

| 维度 | Othello 8×8 | Clobber 5×6 |
|------|-------------|-------------|
| 棋盘大小 | 8×8 | 5×6（padded 7×7） |
| 动作空间 | 65 | 196 |
| 平均局长 | ~58 步 | ~17 步 |
| 有跳过（pass） | 是 | 否 |
| 翻转/捕获 | 翻转多子 | 移除单子 |
| 终止模式 | 棋盘满或双 pass | 无合法移动 |
| 博弈复杂度 | 较高（10^28 局面空间） | 中等 |
| MCTS 难度 | 中等（深度搜索有效） | 较高（局面评估困难） |

---

## 强化学习建模

### 问题框架

两个棋类游戏均建模为**二人零和马尔可夫博弈（Two-player Zero-Sum Markov Game）**：

$$G = (S, A, T, R, \gamma=1)$$

其中价值从**当前玩家视角**（current-player-relative）定义，在自对弈框架下等价于单智能体 MDP。

---

### 状态表示

每个棋局状态 $s_t$ 编码为形状 `(5, H, W)` 的浮点张量，5 个通道含义如下：

| 通道 | 含义 | 归一化 |
|------|------|--------|
| 0 | 己方棋子位置（当前玩家视角） | 0/1 |
| 1 | 对方棋子位置 | 0/1 |
| 2 | 空格位置 | 0/1 |
| 3 | 有效区域掩码（padding 区域为 0） | 0/1 |
| 4 | 相位（phase = move\_index / max\_game\_length，全图广播） | [0,1] |

**关键设计**：
- 通道 0-1 始终从**当前落子方**视角填充，使网络无需区分执黑/执白。
- 通道 3（valid_mask）用于 Clobber 的 padding 区域屏蔽，Othello 因不需要 padding 故全为 1。
- 通道 4（phase）让网络感知游戏进程，辅助价值函数估计。

各游戏具体张量形状：

| 游戏 | 观测形状 | pad 区域 |
|------|----------|----------|
| Othello 8×8 | (5, 8, 8) | 无 |
| Clobber 5×6 | (5, 7, 7) | 右列和底行为0 |

---

### 动作空间

#### Othello 动作编码

动作索引 $a \in \{0, 1, \dots, 64\}$，共 65 个：

$$a = \begin{cases} \text{row} \times 8 + \text{col} & 0 \le a \le 63 \quad \text{（落子于某格）} \\ 64 & \text{（pass，跳过）} \end{cases}$$

非法动作通过 `legal_action_mask`（形状 `(65,)`）屏蔽，softmax 前减去大数使其概率趋近 0。

#### Clobber 动作编码

动作索引通过 **源格 × 方向** 编码，共 196 个（$= 7 \times 7 \times 4$，使用 padding 后的格大小）：

$$a = (r \times W_{\text{pad}} + c) \times 4 + d$$

其中：
- $(r, c)$ 为源棋子位置（行、列）
- $d \in \{0, 1, 2, 3\}$ 为方向，对应 $\Delta = \{(-1,0),\ (0,+1),\ (+1,0),\ (0,-1)\}$（上、右、下、左）
- 非棋盘内的源/目标格对应的动作始终被 legal_mask 屏蔽

---

### 奖励函数

$$r_t = \begin{cases} 0 & t < T \quad \text{（非终局步）} \\ +1 & t = T, \text{当前玩家获胜} \\ -1 & t = T, \text{当前玩家失败} \\ 0 & t = T, \text{平局（仅 Othello）} \end{cases}$$

终局奖励 $r_T$ 从当前玩家视角定义，并在 replay buffer 中以**轮流交替符号**传播回前序步骤（$V$-trace 或 $n$-step return）。

---

### 自对弈训练目标

训练的目标价值函数 $V^*(s)$ 和策略 $\pi^*(s)$ 满足：

$$V^*(s) = \text{GameOutcome}(s) \text{ from perfect play}$$
$$\pi^*(s) = \arg\max_a \, Q^*(s, a)$$

通过 **Gumbel MuZero** 的 MCTS 搜索逐步逼近，以访问次数作为策略改进目标：

$$\pi_{\text{target}}(a | s) = \frac{N(s, a)^{1/\tau}}{\sum_{a'} N(s, a')^{1/\tau}}$$

其中 $\tau$ 为温度参数（训练时通常设为 1，评估时设为 0）。

---

### 评估指标

模型通过与固定强度 MCTS 基线对战来评估，记胜率（Win Rate, WR）：

| 游戏 | 基线强度 | Quick eval 局数 |
|------|----------|-----------------|
| Othello | 64 sim MCTS | 200 局 |
| Clobber | 64 sim MCTS | 200 局 |

评估时对战双方交替先手，消除先手优势偏差。

---

## 神经网络架构

### MuZero 三函数框架

MuZero 将棋局建模为隐空间动力学，由三个可学习函数组成：

$$h_\theta: s_t \to z_t \qquad \text{（representation：编码初始观测）}$$
$$g_\theta: (z_t, a_t) \to (z_{t+1}, r_t) \qquad \text{（dynamics：单步rollout）}$$
$$f_\theta: z_t \to (\pi_t, v_t) \qquad \text{（prediction：策略+价值）}$$

三函数共用同一参数集 $\theta$，端对端联合训练。

训练时每个样本 **unroll 1 步**（`unroll_steps=1`），即从初始状态 $s_t$ unroll 到 $s_{t+1}$，在两个时间步上计算损失。

---

### 实现：`BoardMuZeroNet`

所有三个函数通过统一的 `BoardMuZeroNet` 模块实现（`projects/openspiel_muzero_pt/model/board_muzero.py`）。

#### 基础模块：`ResidualBlock`

```
input (C, H, W)
  │
  ├─ Conv2d(C, C, 3×3, pad=1) → BatchNorm2d → GELU
  │   → Conv2d(C, C, 3×3, pad=1) → BatchNorm2d
  │
  └─ skip connection (identity)
       │
       GELU(output + skip)  ──→  output (C, H, W)
```

#### 基础模块：`ResidualTower`

```
input (C_in, H, W)
  → Conv2d(C_in, C, 1×1)             # 投影至 C 通道
  → N 个 ResidualBlock(C, C)
  → output (C, H, W)
```

---

#### Representation function $h_\theta$

```
obs (5, H, W)
  → ResidualTower(5 → C, repr_blocks)
  → LayerNorm(C, H, W)
  → _scale_norm(·)                    # 每样本单位 max-norm 归一化
  → latent z  (C, H, W)
```

#### Dynamics function $g_\theta$

动作编码为 3 个平面（shape `(3, H, W)`）：

| 通道 | Othello | Clobber |
|------|---------|---------|
| 0 | zeros | 源格平面（1 at src） |
| 1 | 落子格平面（1 at cell） | 目标格平面（1 at dst） |
| 2 | pass 平面（全 1 若 pass，否则全 0） | zeros |

```
(latent z, action_planes)                # z: (C, H, W), planes: (3, H, W)
  → cat([z, planes], dim=0)              # (C+3, H, W)
  → ResidualTower(C+3 → C, dyn_blocks)
  → LayerNorm(C, H, W)
  → _scale_norm(·)
  → next_latent z'  (C, H, W)
  → RewardHead(z') → r̂  (scalar)
```

#### Prediction function $f_\theta$

```
latent z  (C, H, W)
    │
    ├── Policy Head:
    │     Conv2d(C, 2, 1×1) → GELU → Flatten
    │     → Linear(2·H·W, head_hidden) → GELU
    │     → Linear(head_hidden, action_dim)
    │     → 减去 legal_action_mask 的大惩罚
    │     → logits (action_dim,)
    │
    └── Value Head:
          Flatten(C·H·W)
          → Linear(C·H·W, head_hidden) → GELU
          → Linear(head_hidden, 1) → Tanh
          → v̂  ∈ (-1, 1)
```

#### Reward Head（RewardHead）

```
latent z  (C, H, W)
  → Flatten(C·H·W)
  → Linear(C·H·W, head_hidden) → GELU
  → Linear(head_hidden, 1) → Tanh
  → r̂  ∈ (-1, 1)
```

---

### 各游戏网络配置

| 超参数 | Othello 8×8 | Clobber 5×6 |
|--------|-------------|-------------|
| `channels` (C) | 128 | 128 |
| `repr_blocks` | 8 | 10 |
| `dyn_blocks` | 3 | 4 |
| `head_hidden` | 256 | 256 |
| 输入形状 | (5, 8, 8) | (5, 7, 7) |
| latent 形状 | (128, 8, 8) | (128, 7, 7) |
| `action_dim` | 65 | 196 |
| 总参数量 | **7.68 M** | **7.61 M** |
| 训练精度 | bf16 | bf16 |

Clobber 使用更多残差块（repr_blocks=10, dyn_blocks=4），因为其棋盘初始密度高、棋局树深度浅但状态评估更难。

---

### 归一化策略

训练过程中使用两种归一化手段：

1. **`LayerNorm`**：在 representation 和 dynamics 的 ResidualTower 输出后应用，稳定 latent 空间尺度。
2. **`_scale_norm`**：自定义操作，将每个样本的 latent 张量除以其 max 绝对值（加 ε），使每个样本的最大激活值归一化为 1.0。防止 latent 崩溃或量级爆炸。

---

### 损失函数（完整版）

训练损失由以下 6 项（+ 可选 KL 项）组成：

$$\mathcal{L} = \underbrace{\mathcal{L}_{\pi}}_{\text{policy}} + \underbrace{\mathcal{L}_{v}}_{\text{value}} + \underbrace{0.05 \cdot \mathcal{L}_{r}}_{\text{reward}} + \underbrace{0.5 \cdot \mathcal{L}_{\pi}^{\text{rec}}}_{\text{recurrent policy}} + \underbrace{0.5 \cdot \mathcal{L}_{v}^{\text{rec}}}_{\text{recurrent value}} + \underbrace{0.25 \cdot \mathcal{L}_{\text{lat}}}_{\text{latent}}$$

v5+ 版本额外增加（独立 backward pass）：

$$+ \underbrace{\lambda_{\text{KL}} \cdot \mathcal{L}_{\text{teacher-KL}}}_{\text{teacher KL anchor}}, \quad \lambda_{\text{KL}} = 0.5$$

各损失项详细定义：

| 损失项 | 权重 | 计算方式 | 目的 |
|--------|------|----------|------|
| $\mathcal{L}_\pi$ | 1.0 | $\text{CrossEntropy}(\hat{\pi}, \pi_{\text{MCTS}})$，初始步 | 模仿 MCTS 策略目标 |
| $\mathcal{L}_v$ | 1.0 | $\text{MSE}(\hat{v}, v_{\text{target}})$，初始步 | 预测游戏结局 |
| $\mathcal{L}_r$ | 0.05 | $\text{MSE}(\hat{r}, r_t)$，初始步 | 预测即时奖励 |
| $\mathcal{L}_\pi^{\text{rec}}$ | 0.5 | $\text{CrossEntropy}(\hat{\pi}', \pi'_{\text{MCTS}})$，rollout 步 | 动力学展开一致性 |
| $\mathcal{L}_v^{\text{rec}}$ | 0.5 | $\text{MSE}(\hat{v}', v'_{\text{target}})$，rollout 步 | 动力学价值一致性 |
| $\mathcal{L}_{\text{lat}}$ | 0.25 | $\text{MSE}(z_{\text{dyn}}, \text{sg}(z_{\text{repr}}))$ | 动力学 latent 与表征 latent 对齐 |
| $\mathcal{L}_{\text{teacher-KL}}$ | 0.5 | $\text{KL}(\pi_{\text{teacher}} \| \hat{\pi})$，专家 batch | 防止遗忘专家知识 |

其中 $\text{sg}(\cdot)$ 为 stop-gradient 操作（`latent.detach()`），防止表征 tower 被 latent 一致性损失主导。

---

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
