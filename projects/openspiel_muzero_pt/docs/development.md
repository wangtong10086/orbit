# Development

## 开发目标

这个子树优先保证三件事：

1. 数学语义正确
2. 真实运行路径可验证
3. 新增游戏时尽量少改 runtime / search 主干

## 本地开发环境

推荐环境：

- `./.venv-muzero`
  运行测试和本地 smoke
- `./.venv-all`
  做 compile / 辅助脚本检查

常用命令：

```bash
source .venv-muzero/bin/activate
export PYTHONPATH=/home/ubuntu/affine-swarm
```

## 测试命令

完整回归：

```bash
./.venv-muzero/bin/python -m pytest -q projects/openspiel_muzero_pt/tests
```

静态编译检查：

```bash
./.venv-all/bin/python -m compileall projects/openspiel_muzero_pt
```

## 修改代码时的建议顺序

### 改游戏表示

先看：

- [`games/game_spec.py`](../games/game_spec.py)
- [`games/affine_registry.py`](../games/affine_registry.py)
- [`games/action_codecs.py`](../games/action_codecs.py)
- [`games/encoders.py`](../games/encoders.py)
- [`games/adapters.py`](../games/adapters.py)

### 改搜索

先看：

- [`search/tree.py`](../search/tree.py)
- [`search/puct.py`](../search/puct.py)
- [`search/gumbel_root.py`](../search/gumbel_root.py)
- [`search/batched_search.py`](../search/batched_search.py)

### 改 online runtime

先看：

- [`runtime/inference.py`](../runtime/inference.py)
- [`runtime/gpu_coordinator.py`](../runtime/gpu_coordinator.py)
- [`runtime/settings.py`](../runtime/settings.py)
- [`pipelines/selfplay_actor.py`](../pipelines/selfplay_actor.py)
- [`pipelines/train_online.py`](../pipelines/train_online.py)

## 调试建议

### 训练不推进

优先检查：

- `online.progress.json` 是否还在更新
- `online.events.jsonl` 是否还有新的 `selfplay_chunk`
- actor 是否报错并写回 `type=error`
- coordinator 进程是否还活着

### GPU 利用率低

优先检查：

- `live_queue_depth`
- `selfplay_chunk` 到达间隔
- `actor_workers`
- `parallel_games_per_actor`
- `runtime.gpu_coordinator.initial/recurrent_max_batch_items`

### quick eval 长时间无结果

优先检查：

- `quick_eval.process.log`
- `quick_eval.progress.json`
- baseline MCTS 预算是否误用了 official 配置

### value / policy 看起来不学

优先检查：

- 当前玩家视角是否一致
- `next_*` recurrent targets 是否正确生成
- terminal reward / value 是否在同一语义口径上

## 文档更新约定

以下情况需要同步更新文档：

- 新增或删除 config section
- online runtime 拓扑变化
- 评测 gate 规则变化
- 新增游戏 family
- Targon 运行方式变化

最低要求：

- 更新 [`README.md`](../README.md)
- 更新相关专题文档

## 当前不建议做的事

- 在 active path 上引入隐式全局 registry
- 让 pipeline 直接依赖 Targon 细节
- 为了临时跑通把 family 特例散回 `train_online.py` 或 `SearchEngine`
- 把 quick 和 official 预算混在一起
