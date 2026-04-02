# Architecture

## 目标

`openspiel_muzero_pt` 是一个面向 Affine OpenSpiel 棋类任务的 PyTorch Gumbel MuZero 训练栈。

当前架构目标：

- 游戏逻辑直接基于 `pyspiel`
- 网络前向/反向集中在单个 GPU coordinator 进程
- CPU actor 负责环境推进和 Python tree search
- quick eval 与 official eval 显式分层
- 新增游戏时优先复用 runtime / search / replay 主路径，而不是复制 Othello 特例

## 目录分层

### `games/`

负责游戏契约和 OpenSpiel 适配层。

- [`game_spec.py`](../games/game_spec.py)
  每个游戏变体的静态定义。
- [`affine_registry.py`](../games/affine_registry.py)
  当前注册的 Othello / Hex / Clobber 任务。
- [`action_codecs.py`](../games/action_codecs.py)
  OpenSpiel 动作和 dense action id 之间的映射。
- [`encoders.py`](../games/encoders.py)
  每个 family 的棋盘编码逻辑。
- [`adapters.py`](../games/adapters.py)
  OpenSpiel 交互入口。负责 `build_game / new_initial_state / encode_state / legal_action_mask / create_affine_mcts_bot`。

设计约束：

- `adapter` 保持轻量，只做 OpenSpiel 协调和通用包装。
- family 特有编码放在 `encoders.py`，避免 `adapters.py` 演化成 God module。

### `model/`

- [`board_muzero.py`](../model/board_muzero.py)
  `BoardMuZeroNet`，包含 `initial_inference` 和 `recurrent_inference`。

网络只关心：

- 输入张量形状
- latent dynamics
- policy / value / reward heads

它不感知具体 OpenSpiel state，也不直接依赖搜索逻辑。

### `search/`

- [`tree.py`](../search/tree.py)
  树节点和边的数据结构。
- [`puct.py`](../search/puct.py)
  选子和 backup 规则。
- [`gumbel_root.py`](../search/gumbel_root.py)
  root shortlist / sequential halving。
- [`batched_search.py`](../search/batched_search.py)
  batched root search 主入口。

设计约束：

- `SearchEngine` 依赖 `ModelInferenceClient`，不直接依赖具体模型实例。
- 这样本地测试可以用 local client，online 则走 brokered client。

### `replay/`

- [`expert_buffer.py`](../replay/expert_buffer.py)
  expert shard 读取和样本打包。
- [`ring_buffer.py`](../replay/ring_buffer.py)
  live replay 的预分配 ring buffer。

当前策略：

- expert 数据来自 `label_with_mcts.py`
- live 数据来自 `selfplay_actor.py`
- learner 端混采 expert + live

### `runtime/`

- [`inference.py`](../runtime/inference.py)
  local / brokered inference client 抽象。
- [`gpu_coordinator.py`](../runtime/gpu_coordinator.py)
  单 GPU coordinator，集中处理 search inference 和 train batch。
- [`settings.py`](../runtime/settings.py)
  online runtime 配置解析。

这是 online 闭环和 warm-start 的最大边界差异。

warm-start：

- 单进程模型训练
- 不走 broker runtime

online：

- CPU actors
- centralized GPU coordinator
- quick eval 独立进程

### `pipelines/`

- [`build_state_corpus.py`](../pipelines/build_state_corpus.py)
- [`label_with_mcts.py`](../pipelines/label_with_mcts.py)
- [`warmstart.py`](../pipelines/warmstart.py)
- [`selfplay_actor.py`](../pipelines/selfplay_actor.py)
- [`train_online.py`](../pipelines/train_online.py)
- [`evaluate_vs_affine_mcts.py`](../pipelines/evaluate_vs_affine_mcts.py)

这些文件共同构成从离线 teacher 数据到 online 自博弈闭环的真实执行路径。

## 在线训练数据流

```text
CPU actor(s)
  -> pyspiel state
  -> SearchEngine
  -> BrokeredInferenceClient
GPU coordinator
  -> initial / recurrent inference
  -> train_batch
train_online
  -> ArrayRingBuffer
  -> expert/live 混采
  -> BrokeredTrainClient
  -> checkpoint / quick eval
```

## 配置分层

配置按 ownership 拆分：

- `game`
  选择任务 id 和 family。
- `model`
  网络宽度、深度、head 维度。
- `search`
  self-play / reanalyse / eval 搜索预算。
- `optimizer`
  学习率、权重衰减、梯度裁剪。
- `train`
  learner cadence 和 checkpoint / eval cadence。
- `actors`
  CPU self-play 并行度。
- `runtime.gpu_coordinator`
  GPU batching / snapshot sync。
- `buffers`
  replay 容量。
- `corpus`
  cheap state corpus 生成。
- `expert`
  expert labeling teacher 预算。
- `eval`
  quick / official 评测门控。

## 当前已知边界

- 树搜索仍然是 Python 实现，不是 CUDA tree。
- OpenSpiel 环境推进仍然是 CPU 路径。
- quick eval 仍使用当前 Affine baseline MCTS。
- 当前最成熟的真实运行路径仍是 Othello；Hex / Clobber 已完成结构接入，但尚未做与 Othello 同等级的真机长跑验证。
