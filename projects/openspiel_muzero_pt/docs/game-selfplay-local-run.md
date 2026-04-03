# GAME Self-Play Local Long-Run

这份文档只描述当前本地长跑训练怎么启动、怎么看、怎么恢复，以及当前 runtime 的实际行为。

## 入口

本地 7 卡并行 launcher:

- [`scripts/game/local_parallel_selfplay_longrun.sh`](../scripts/game/local_parallel_selfplay_longrun.sh)

训练脚本入口:

- [`scripts/game/targon_game_selfplay_longrun.py`](../scripts/game/targon_game_selfplay_longrun.py)

单游戏核心实现:

- [`forge/data/game_policy_models/selfplay.py`](../forge/data/game_policy_models/selfplay.py)
- [`forge/data/game_policy_models/selfplay_runtime.py`](../forge/data/game_policy_models/selfplay_runtime.py)
- [`forge/data/game_policy_models/selfplay_control.py`](../forge/data/game_policy_models/selfplay_control.py)

## 当前运行模型

外层并行:

- 7 个 game 各自独立训练进程
- 默认一 game 绑定一张 GPU

单 game 内部分工:

- CPU actor 负责 OpenSpiel 环境推进、树搜索、replay 样本组装
- GPU evaluator 负责批量 policy/value 前向
- learner 负责消费 replay、更新 `latest` checkpoint

当前 replay 主路径:

- 有 CUDA 时优先走共享 GPU batched evaluator
- 多 actor 时走多进程 CPU actor + 父进程 GPU batching service
- 无 CUDA 时回退到旧的本地模型评估路径

这意味着 GPU 利用率通常是脉冲式的，不会像纯 dense training 那样持续高位。CPU 仍会维持较高占用，因为 OpenSpiel state transition 和树搜索主体还在 CPU。

## Gate 与 Phase

当前一个 learner round 的顺序是：

1. `replay`
2. `learn`
3. `quick_eval`
4. `teacher_eval`
   先跑 cheap teacher gate，再决定是否进入 full teacher gate
5. `sync`

当前 phase:

- `ramp`
  训练早期，simulation budget 更低，优先产 replay
- `stabilize`
  中期默认阶段
- `gate_push`
  接近 teacher gate 时，提高 search budget

cheap teacher gate 是内部运行时概念，不是公开 CLI opponent。公开的 eval opponent 仍是 `teacher | best | checkpoint`。

## 启动与控制

常用命令：

```bash
cd /home/xmyf/affine-swarm
./scripts/game/local_parallel_selfplay_longrun.sh launch
./scripts/game/local_parallel_selfplay_longrun.sh status
./scripts/game/local_parallel_selfplay_longrun.sh tail othello
./scripts/game/local_parallel_selfplay_longrun.sh stop
```

默认 job:

- `formal-7gpu-teacher90-streak3`

默认输出根目录:

- `artifacts/game_local_runs/<job>/`

## 输出结构

每个 game 的输出目录:

- `outputs/<game>/latest/`
- `outputs/<game>/best/`
- `outputs/<game>/history/`
- `outputs/<game>/arena/`
- `outputs/<game>/replay/`
- `outputs/<game>/replay_meta/`
- `outputs/<game>/status.json`
- `outputs/<game>/heartbeat.json`

launcher 额外目录:

- `logs/`
- `configs/`
- `pids/`

## 如何看状态

`heartbeat.json` 适合看运行中状态，典型字段：

- `phase`
- `rows_generated_total`
- `replay_states_per_sec`
- `learner_steps_completed`
- `eval_batch_size`
- `eval_queue_depth`
- `eval_batches_per_sec`
- `gpu_util_avg_5m`

`status.json` 适合看 round 级结果，典型字段：

- `learner_updates`
- `phase_replay_rows`
- `last_quick_win_rate`
- `last_cheap_teacher_win_rate`
- `last_teacher_win_rate`
- `teacher_pass_streak`
- `full_teacher_games_played`
- `evaluator_version`

注意:

- `heartbeat.json` 在 replay 阶段会持续更新
- `status.json` 通常只在 learner round 完成后更新
- 日志文件是追加写，`tail` 里可能包含重启前的旧错误

## 恢复语义

默认 `resume=1`。

中断后重新执行 `launch` 会继续使用已有输出目录：

- 从 `latest/` checkpoint 恢复模型
- 继续沿用已有 `best/`
- 继续使用 `status.json` 里的 learner / gate 进度
- 继续沿用 replay window 与 replay meta

如果设置了 `AFFINE_GAME_POLICY_REPO`，会按当前同步策略把 `latest / best / arena / replay_meta / status` 同步到 Hugging Face；否则就是纯本地恢复。
