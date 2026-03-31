# GAME Generators

这份文档只回答四个问题：

1. `GAME` 现在有哪些游戏和默认 generator family
2. `policy_model` 训练子系统的模块边界是什么
3. 当前 self-play 训练和评估怎么跑
4. 哪些命令和脚本是当前仍在使用的入口

## 当前游戏与默认 family

当前 7 个游戏：

- `goofspiel`
- `leduc_poker`
- `liars_dice`
- `gin_rummy`
- `othello`
- `hex`
- `clobber`

默认 generator family：

- `othello / hex / clobber`
  - `mcts`
- `goofspiel / leduc_poker`
  - `cfr` offline snapshot
- `liars_dice / gin_rummy`
  - `mccfr` offline snapshot

`policy_model` 是额外采样后端，不替代默认 teacher family：

- `forge data game-gen --generator-source default`
  - 按 registry 使用传统算法 family
- `forge data game-gen --generator-source policy_model`
  - 使用训练好的小型 action model

## 模块边界

主入口：

- [forge/data/game_gen.py](../forge/data/game_gen.py)
  - collector 级调度
- [forge/data/game_trajectory_generators.py](../forge/data/game_trajectory_generators.py)
  - registry 与 generator source 解析

generator family 实现：

- [forge/data/game_generators/search_generators.py](../forge/data/game_generators/search_generators.py)
- [forge/data/game_generators/policy_generators.py](../forge/data/game_generators/policy_generators.py)
- [forge/data/game_generators/model_generators.py](../forge/data/game_generators/model_generators.py)

`policy_model` 训练子系统：

- [forge/data/game_policy_models/featurizers.py](../forge/data/game_policy_models/featurizers.py)
  - state feature 定义
- [forge/data/game_policy_models/models.py](../forge/data/game_policy_models/models.py)
  - per-game policy/value network
- [forge/data/game_policy_models/inference.py](../forge/data/game_policy_models/inference.py)
  - 推理与状态查询
- [forge/data/game_policy_models/selfplay.py](../forge/data/game_policy_models/selfplay.py)
  - self-play 主流程、search、replay 组装
- [forge/data/game_policy_models/selfplay_runtime.py](../forge/data/game_policy_models/selfplay_runtime.py)
  - batched GPU evaluator、多进程 replay runtime
- [forge/data/game_policy_models/selfplay_control.py](../forge/data/game_policy_models/selfplay_control.py)
  - phase、gate、arena report 辅助逻辑
- [forge/data/game_policy_models/artifacts.py](../forge/data/game_policy_models/artifacts.py)
  - artifact、runtime profile、status/heartbeat 落盘

边界约束：

- `game_gen.py` 不直接关心某个 game 用哪种 family
- registry 负责把 `default / policy_model` 解析成具体实现
- `policy_model` 子系统不负责 collector orchestration

## 当前 self-play 路线

训练主链路：

1. self-play root search
2. replay buffer build
3. policy/value train
4. quick gate vs `best`
5. cheap teacher gate
6. full teacher gate
7. `best` promotion

teacher 的角色：

- baseline / arena 对手
- 晋级门槛
- 回归验证

teacher 不再直接作为训练样本来源。

## 两类游戏的当前实现

### Perfect-Info

适用：

- `othello`
- `hex`
- `clobber`

当前实现：

- board-plane featurizer
- residual CNN / ResNet policy-value model
- PUCT search
- self-play replay
- quick gate vs `best`
- teacher gate vs MCTS baseline

当前 replay/runtime：

- 单 game 独立训练进程
- replay 优先走共享 GPU batched evaluator
- 多 actor 时使用多进程 CPU actor + 父进程 GPU batching service
- learner 单写 `latest / best`

### Imperfect-Info

适用：

- `leduc_poker`
- `goofspiel`
- `liars_dice`
- `gin_rummy`

当前实现：

- structured feature / fallback feature
- residual MLP policy-value model
- AlphaZero-inspired root search
- self-play replay
- quick gate vs `best`
- teacher gate vs exact baseline

当前兼容性说明：

- `goofspiel`
  - turn-based conversion + PUCT
- `liars_dice`
  - OpenSpiel 缺 `ResampleFromInfostate()` 时走 fallback
- `gin_rummy`
  - 缺 tensor observation 时走 fallback feature

## 当前运行时行为

单 game 内部分工：

- CPU
  - OpenSpiel 环境推进
  - 树搜索
  - replay 样本组装
- GPU
  - batched policy/value evaluator
  - learner update

因此常见现象是：

- CPU 占用高
- GPU 利用率是脉冲式
- `heartbeat.json` 已更新但 `status.json` 还没动

这通常表示训练处在 replay 阶段，不等于卡死。

本地 7 卡长跑 launcher 与状态字段说明见 [game-selfplay-local-run.md](game-selfplay-local-run.md)。

## 当前公开命令

训练与评估：

- `forge data game-selfplay-train --game <game>`
- `forge data game-selfplay-resume --game <game>`
- `forge data game-selfplay-status --game <game>`
- `forge data game-selfplay-eval --game <game> --opponent teacher|best|checkpoint`
- `forge data game-policy-model-status --game <game>`

采样与 teacher：

- `forge data game-gen --game <game> --generator-source policy_model`
- `forge data game-build-policy --game <game>`
- `forge data game-upload-teacher --game <game> --repo <private-model-repo>`

远程长跑：

- `forge remote machine -m <machine> game-longrun launch|status|stop`

## 当前脚本

本地长跑：

- [scripts/game/local_parallel_selfplay_longrun.sh](../scripts/game/local_parallel_selfplay_longrun.sh)

rental 开发脚本：

- [scripts/game/rental_prepare_policy_env.sh](../scripts/game/rental_prepare_policy_env.sh)
- [scripts/game/rental_sync_policy_code.sh](../scripts/game/rental_sync_policy_code.sh)
- [scripts/game/rental_run_teacher_build.sh](../scripts/game/rental_run_teacher_build.sh)
- [scripts/game/rental_run_selfplay_train.sh](../scripts/game/rental_run_selfplay_train.sh)
- [scripts/game/rental_run_selfplay_eval.sh](../scripts/game/rental_run_selfplay_eval.sh)
- [scripts/game/rental_run_policy_sample_smoke.sh](../scripts/game/rental_run_policy_sample_smoke.sh)
- [scripts/game/targon_game_smoke.py](../scripts/game/targon_game_smoke.py)

## 当前验证结论

已经真实打通：

- `leduc_poker`
  - self-play train + teacher eval + `policy_model` sampling
- `goofspiel`
  - self-play train + `policy_model` sampling
- `othello`
  - 本地最小 self-play smoke + `policy_model` sampling

已经打通训练主链路，但还缺更长时间 gate 验证：

- `hex`
- `clobber`
- `liars_dice`
- `gin_rummy`
