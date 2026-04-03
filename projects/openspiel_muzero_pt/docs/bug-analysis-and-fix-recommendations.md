# MuZero 实现 Bug 分析与修复建议

本文档基于对 `projects/openspiel_muzero_pt/` 全部源码的深入审计，系统分析当前 MuZero 实现中存在的 bug、设计缺陷及其对训练效率和收敛性的影响，并给出具体修复建议。

---

## 一、确认的 Bug（按严重程度排序）

### BUG-1 [严重] 在线流式自博弈 value_target 使用搜索估值而非游戏结果

**位置**: `pipelines/selfplay_actor.py` — `_advance_selfplay_slots_streaming()`

**问题**:
在流式自博弈路径（在线训练实际使用的路径）中，非终局状态的 `value_target` 被设置为当前搜索树的 `root_value` 估值：

```python
# selfplay_actor.py L346
current_row = {
    ...
    "value_target": float(result.root_value[index]),
    ...
}
```

而 `root_value` 是从搜索树的边 Q 值加权计算的：

```python
# batched_search.py L239
weighted_value = 0.0
for action, edge in root.edges.items():
    weighted_value += float(policy[int(action)]) * float(edge.q_root)
root_values.append(float(weighted_value))
```

这意味着：
- 对于弱模型/随机模型，`root_value` 本质上是噪声
- 模型在用**自己的预测值**训练自己 → 自增强反馈回路
- 只有终局状态使用了真实的 `final_returns`

**对比**: 非流式路径 `_advance_selfplay_slots()` + `_finalize_completed_game()` 正确地在游戏结束后为**所有**位置回填 `final_returns[player]`。

**影响**: 这是**收敛失败的根本原因**。Value head 无法学到正确的状态评估，因为它的训练目标就是自身的噪声预测，导致策略改进环路断裂。

**修复方案**:

方案 A（推荐）：延迟发射 + 游戏结果回填
```python
# 在流式路径中，仅在游戏完成时才发射所有该游戏的样本
# 将 value_target 统一替换为 final_returns[player]
# 这需要在 slot 中暂存所有行，等游戏终止后一起发射
```

方案 B：使用 n-step bootstrapped return
```python
# 对非终局状态，使用 n-step TD target:
# value_target = sum(gamma^i * r_i, i=0..n-1) + gamma^n * V(s_{t+n})
# 其中 V(s_{t+n}) 是搜索得到的根值
# 这比裸的 root_value 好，但仍依赖模型估值
```

方案 C：混合策略
```python
# 立即发射样本但使用 root_value 作为临时目标
# 在游戏完成后发送一条 "correction" 消息
# 重放缓冲区根据 episode_id + move_index 回填真实 value
```

---

### BUG-2 [严重] 重放缓冲区采样每次复制完整缓冲区

**位置**: `replay/ring_buffer.py` — `sample_batch()`

**问题**:
```python
def sample_batch(self, batch_size: int, *, rng: np.random.Generator) -> dict[str, np.ndarray]:
    logical = self.materialize()  # 复制整个缓冲区!
    indices = rng.integers(0, self._size, size=max(int(batch_size), 1))
    return {key: value[indices] for key, value in logical.items()}
```

`materialize()` 在每次采样时创建完整缓冲区的有序拷贝。对于 `live_capacity=2,000,000`（配置中的值），这意味着：
- Othello obs shape `(5, 8, 8)` × float32 = 1280 bytes/row
- 每次采样复制 ~2.5 GB 数据（包含 obs, next_obs, policy_target 等所有字段）
- 每个训练步都执行此操作

**影响**: 严重的 CPU 瓶颈，训练吞吐量可能降低一个数量级。GPU 大部分时间在等待 CPU 完成缓冲区复制。

**修复方案**:
```python
def sample_batch(self, batch_size: int, *, rng: np.random.Generator) -> dict[str, np.ndarray]:
    if self._storage is None or self._size == 0:
        raise ValueError("Cannot sample from an empty ring buffer")
    # 直接在物理存储上采样，用模运算转换逻辑索引到物理索引
    logical_indices = rng.integers(0, self._size, size=max(int(batch_size), 1))
    physical_indices = (self._head + logical_indices) % self.capacity
    return {key: value[physical_indices] for key, value in self._storage.items()}
```

---

### BUG-3 [中等] PUCT 的 parent_visit_count 使用候选边总和而非节点总访问

**位置**: `search/puct.py` — `select_child()`

**问题**:
```python
def select_child(node: SearchNode, *, c_puct: float) -> SearchEdge:
    candidates = node.candidate_edges()
    maximize_root = int(node.current_player) == int(node.root_player)
    parent_visit_count = sum(edge.visit_count for edge in candidates)
    ...
```

`candidate_edges()` 在根节点时返回 shortlist 子集：
```python
def candidate_edges(self) -> list[SearchEdge]:
    if self.depth == 0 and self.root_shortlist is not None:
        shortlisted = [self.edges[int(action)] for action in self.root_shortlist if int(action) in self.edges]
        if shortlisted:
            return shortlisted
    return list(self.edges.values())
```

当 Sequential Halving 活跃时，`candidates` 可能只是所有 edge 的子集。标准 PUCT 公式中的 $N(\text{parent})$ 应该是父节点的**总**访问次数，而非仅候选边的总和。

**影响**: 探索奖励被低估，搜索树过早利用（exploit-heavy），特别在 Othello 这种高分支因子游戏中影响搜索质量。

**修复方案**:
```python
def select_child(node: SearchNode, *, c_puct: float) -> SearchEdge:
    candidates = node.candidate_edges()
    maximize_root = int(node.current_player) == int(node.root_player)
    parent_visit_count = node.visit_count  # 使用节点总访问次数
    ...
```

---

### BUG-4 [中等] 动力学模型 action_planes 第 0 通道始终为零

**位置**: `games/action_codecs.py` — `OthelloActionCodec`

**问题**: 3 通道 action planes 编码中：
- 通道 0：始终全零（未使用）
- 通道 1：落子位置
- 通道 2：pass 操作标记

动力学网络的输入是 `latent (128ch) + action_planes (3ch) = 131 ch`，其中 action_planes 有 1/3 通道浪费。

**影响**: 浪费了动力学模型的输入通道容量。虽然不是致命 bug，但减少了可用信息密度。

**修复方案**:
```python
# 方案 A: 将通道 0 编码为 "合法性" 或 "当前玩家" 信息
# 方案 B: 减少为 2 通道 action planes，调整 dynamics tower input channels
# 方案 C（推荐）: 通道 0 编码当前玩家标识（全 0 或全 1）
```

---

### BUG-5 [中等] 奖励几乎全为零，reward head 训练信号极度稀疏

**位置**: `games/adapters.py` — `current_player_reward()`

**问题**:
```python
def current_player_reward(self, state_before, state_after, player: int) -> float:
    if not state_after.is_terminal():
        return 0.0
    returns = state_after.returns()
    return float(returns[int(player)])
```

棋类游戏中只有终局状态有非零奖励。在 Othello 平均游戏长度 ~60 步的情况下，reward_target 在 ~98% 的训练样本中为 0.0。

**影响**: reward head 几乎学不到任何有意义的信号，但其损失项（权重 0.25）仍然在反向传播中产生梯度，可能干扰其他网络组件的学习。

**修复方案**:
```python
# 方案 A（推荐）: 将 reward loss 权重降到 0.05 或更低
loss = (
    loss_policy
    + loss_value
    + 0.05 * loss_reward       # 降低 reward 权重
    + 0.5 * loss_recurrent_policy
    + 0.5 * loss_recurrent_value
    + 0.25 * loss_latent
)

# 方案 B: 使用中间奖励信号（如子力差变化）
# 方案 C: 完全移除 reward head，棋类游戏不需要
```

---

## 二、设计缺陷及其对收敛性的影响

### DESIGN-1 [高] latent space 使用 tanh 压缩导致梯度消失

**位置**: `model/board_muzero.py`

```python
def representation(self, obs: torch.Tensor) -> torch.Tensor:
    return torch.tanh(self.representation_tower(obs))

def dynamics(self, latent: torch.Tensor, action_planes: torch.Tensor) -> tuple[...]:
    next_latent = torch.tanh(self.dynamics_tower(torch.cat([latent, action_planes], dim=1)))
    ...
```

**问题**: tanh 在 ±1 附近梯度趋近于零。在多步展开（recurrent inference）中，latent 通过 tanh 多次压缩，导致：
1. 梯度信号在展开步数增加时指数衰减
2. latent consistency loss 更难优化（两端都被 tanh 压缩）
3. 特征值被挤压到 [-1, 1]，信息容量受限

**修复方案**:
```python
# 方案 A（推荐）: 使用 scale normalization 代替 tanh
def representation(self, obs: torch.Tensor) -> torch.Tensor:
    h = self.representation_tower(obs)
    return h / (h.norm(dim=1, keepdim=True).clamp(min=1.0))

# 方案 B: 使用 LayerNorm
def representation(self, obs: torch.Tensor) -> torch.Tensor:
    h = self.representation_tower(obs)
    return self.repr_norm(h)  # nn.LayerNorm

# 方案 C: 移除 latent 激活，依赖 BatchNorm 稳定分布
```

---

### DESIGN-2 [高] 搜索模型同步间隔过长

**位置**: `runtime/gpu_coordinator.py` — `snapshot_sync_interval=2000`

**问题**: 训练模型每 2000 步才同步到搜索模型。在 `othello_h200x2_online.yaml` 配置下：
- `batch_size=2048`, `workers=12`, `active_games_per_actor=32`
- 自博弈产生的数据是用 2000 步之前的旧模型生成的
- 策略滞后（policy lag）严重，自博弈数据很快过时

**影响**: 等效于训练时使用了大量 off-policy 数据，但没有任何 importance sampling 修正。

**修复方案**:
```yaml
# 将 snapshot_sync_interval 降到 50-200
runtime:
  gpu_coordinator:
    snapshot_sync_interval: 100
```

---

### DESIGN-3 [高] 没有学习率调度策略

**位置**: `runtime/gpu_coordinator.py` — optimizer 创建

```python
optimizer = torch.optim.AdamW(
    train_model.parameters(),
    lr=float(optimizer_cfg.get("lr_online", 5.0e-4)),
    weight_decay=float(optimizer_cfg.get("weight_decay", 1.0e-4)),
)
```

**问题**: 固定学习率 5e-4 贯穿整个训练过程。现代深度强化学习通常需要：
- 初始热身（warm-up）阶段
- 余弦退火或阶梯衰减

**影响**: 训练早期学习率过大导致不稳定，后期学习率过大导致抖动。

**修复方案**:
```python
# 添加余弦退火调度
scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
    optimizer,
    T_max=total_steps,
    eta_min=1e-5,
)
# 每个 train_batch 后 scheduler.step()
```

---

### DESIGN-4 [高] 没有数据增强（Othello D4 对称群）

**问题**: Othello 棋盘有 D4 对称群（8 种对称变换：4 旋转 + 4 翻转）。代码已有 `OthelloActionCodec.remap_under_symmetry()` 支持所有 8 种变换，但训练中从未使用。

**影响**: 有效训练数据量减少 8 倍，样本效率严重降低。

**修复方案**:
```python
# 在 learner.train_batch 中添加随机对称变换
def _augment_batch(self, batch, rng):
    symmetries = ["identity", "rot90", "rot180", "rot270", "flip_h", "flip_v", "diag", "anti_diag"]
    sym = rng.choice(symmetries)
    if sym == "identity":
        return batch
    # 对 obs, next_obs, legal_mask, policy_target, action 等应用对称变换
    ...
```

---

### DESIGN-5 [中等] 重放缓冲区使用均匀采样

**问题**: 没有优先经验回放（Prioritized Experience Replay）。所有转移的采样概率相同。

**影响**: 重要的转移（如接近胜负分水岭的状态）与无信息状态被等概率采样，学习效率低。

**修复方案**:
```python
# 添加基于 TD error 或 loss 的优先级采样
# 或者使用简单的加权策略：终局附近的样本权重更高
```

---

### DESIGN-6 [中等] BatchNorm 在在线训练中的统计不匹配

**问题**: 
- 训练模型的 BatchNorm 运行统计基于混合的 expert + live 批次
- 搜索模型在 `eval()` 模式下使用训练模型的运行统计
- 但搜索模型的实际输入分布（来自自博弈中的各种状态）可能与训练批次分布不同

**修复方案**: 
```python
# 方案 A: 将 BatchNorm 替换为 LayerNorm（推荐）
# 方案 B: 在同步时重新校准 BN 统计
# 方案 C: 在搜索模型中也使用 train() 模式（但需要足够大的 batch）
```

---

### DESIGN-7 [中等] 训练/评估搜索预算不匹配

已在诊断文档中记录，此处汇总：

| 组件 | 模拟次数 | Rollouts |
|------|---------|----------|
| 在线自博弈 | 64 | — |
| 教师标注 | 64 | 8 |
| Quick eval agent | 64 | — |
| Quick eval baseline | 128 | 8 |
| Official eval baseline | 1000 | 20 |

训练信号来自 64-sim 搜索，但评估对手用了 128-1000 sim + 多 rollout。训练出的策略在面对更强的评估对手时注定劣势。

**修复方案**:
```yaml
# 提高训练搜索预算或降低评估预算
search:
  train_num_simulations: 128  # 提升自博弈搜索强度

eval:
  quick_baseline_simulations: 64  # 降低到与训练一致
  quick_baseline_rollouts: 4
```

---

## 三、性能瓶颈

### PERF-1 专家缓冲区每次采样时加载全部分片

**位置**: `replay/expert_buffer.py` — `sample_batch()` 调用 `load_all()`

```python
def sample_batch(self, batch_size: int, *, rng: np.random.Generator) -> dict[str, np.ndarray]:
    merged = self.load_all()  # 每次合并所有分片
    ...
```

虽然 `_payloads` 有缓存，但 `load_all()` 每次都执行 `np.concatenate`。

**修复方案**: 缓存合并后的结果。

---

### PERF-2 搜索树未使用虚拟损失（Virtual Loss）

**问题**: 当前搜索是串行的——每个 simulation 一次选择一条路径。在 batched 设置下，没有虚拟损失意味着多个 root 可能选择完全相同的路径，导致搜索树展开效率低。

---

## 四、修复优先级排序

| 优先级 | ID | 修复项 | 预期影响 |
|---------|-----|--------|----------|
| P0 | BUG-1 | 修复流式自博弈的 value_target | 解决收敛失败的根本原因 |
| P0 | BUG-2 | 修复 ring buffer 采样效率 | 训练吞吐量提升 5-10x |
| P1 | DESIGN-1 | 替换 tanh latent 压缩 | 改善梯度流动和展开学习 |
| P1 | DESIGN-2 | 降低搜索模型同步间隔 | 减少 off-policy 程度 |
| P1 | BUG-3 | 修复 PUCT parent_visit_count | 改善搜索质量 |
| P2 | DESIGN-3 | 添加学习率调度 | 改善训练稳定性 |
| P2 | DESIGN-4 | 添加 D4 对称增强 | 8x 有效数据量 |
| P2 | DESIGN-7 | 对齐训练/评估搜索预算 | 公平评估 |
| P3 | BUG-5 | 降低 reward loss 权重 | 减少无效梯度 |
| P3 | DESIGN-5 | 优先经验回放 | 提升采样效率 |
| P3 | DESIGN-6 | BatchNorm → LayerNorm | 改善推理一致性 |
| P3 | BUG-4 | 利用 action planes 通道 0 | 微小改善 |

---

## 五、验证计划

修复后的验证步骤：

1. **单元测试**: 确保 `_advance_selfplay_slots_streaming` 输出的 `value_target` 与游戏结果一致
2. **拟合测试**: 用固定小数据集验证模型可以过拟合（loss 降到接近 0）
3. **快速收敛测试**: 在小模型 + 少步数配置下验证 quick eval win rate 是否提升
4. **完整在线训练**: 在 `othello_8x8.yaml` 配置下运行完整在线训练，观察 win rate 趋势

---

## 六、关键代码参考

| 文件 | 相关问题 |
|------|----------|
| `pipelines/selfplay_actor.py` L276-400 | BUG-1 (streaming value_target) |
| `replay/ring_buffer.py` L63-70 | BUG-2 (materialize in sample) |
| `search/puct.py` L19-28 | BUG-3 (parent_visit_count) |
| `model/board_muzero.py` L110-112 | DESIGN-1 (tanh latent) |
| `runtime/gpu_coordinator.py` L261-262 | DESIGN-2 (sync interval) |
| `pipelines/learner.py` L77-85 | BUG-5 (loss weights) |
| `games/action_codecs.py` L67-85 | BUG-4 (action planes) |
