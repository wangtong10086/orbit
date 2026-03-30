# GAME Generators

`GAME` 数据收集现在已经拆成三层：

- collector
- trajectory generator registry
- per-family generator implementation

这样做的目的不是“把脚本搬家”，而是让下面三件事可以独立演进：

- `forge data game-gen` / `forge worker render collect --env GAME` 保持稳定
- 不同游戏可以走不同的传统算法路径
- `policy_model` 可以作为额外采样后端接进来，而不重写 collector

## 当前状态

当前默认 registry 已经不是“全量 random”。

当前 7 个游戏：

- `goofspiel`
- `leduc_poker`
- `liars_dice`
- `gin_rummy`
- `othello`
- `hex`
- `clobber`

当前默认 generator family：

- `othello / hex / clobber`
  - `mcts`
- `leduc_poker / goofspiel`
  - `cfr` offline policy snapshot
- `liars_dice / gin_rummy`
  - `mccfr` offline policy snapshot

当前 `policy_model` 已经作为额外采样方式接入，但不是默认主路径：

- `forge data game-gen --generator-source default`
  - 走 registry 默认传统算法路径
- `forge data game-gen --generator-source policy_model`
  - 走训练好的小型 action model

当前真实验证结论：

- `leduc_poker`
  - self-play train -> teacher eval -> `policy_model` sampling
  - 已经在 rental 上真实打通
- `goofspiel`
  - self-play train -> `policy_model` sampling
  - 已经在 rental 上真实打通
- `liars_dice / gin_rummy`
  - self-play 训练已经可以启动并写出 `latest / best / replay_meta`
  - 当前还没有完成长期 teacher gate 验证
  - `liars_dice` 会在 OpenSpiel 缺少 `ResampleFromInfostate()` 时回退到 policy-prior rollout
  - `gin_rummy` 会在缺少 tensor observation 时回退到 hashed string features

## 模块边界

核心文件：

- Registry: [game_trajectory_generators.py](/home/wangtong/affine-swarm/forge/data/game_trajectory_generators.py)
- Collector glue: [game_gen.py](/home/wangtong/affine-swarm/forge/data/game_gen.py)
- Search generators: [search_generators.py](/home/wangtong/affine-swarm/forge/data/game_generators/search_generators.py)
- Exact policy-snapshot generators: [policy_generators.py](/home/wangtong/affine-swarm/forge/data/game_generators/policy_generators.py)
- Trained policy-model generator: [model_generators.py](/home/wangtong/affine-swarm/forge/data/game_generators/model_generators.py)
- Policy-model training subsystem:
  - [featurizers.py](/home/wangtong/affine-swarm/forge/data/game_policy_models/featurizers.py)
  - [models.py](/home/wangtong/affine-swarm/forge/data/game_policy_models/models.py)
  - [inference.py](/home/wangtong/affine-swarm/forge/data/game_policy_models/inference.py)
  - [selfplay.py](/home/wangtong/affine-swarm/forge/data/game_policy_models/selfplay.py)

职责分工：

- `game_gen.py`
  - 负责 collector 级调度
  - 负责 oversampling、seed 批次、按游戏拼接 staging 文件
  - 不负责具体对局策略
- `game_trajectory_generators.py`
  - 负责“某个游戏当前应该用哪个 family”
  - 负责把 `default / policy_model` 这样的 generator source 解析到明确实现
- `game_generators/*.py`
  - 负责真实 rollout
  - 每个 family 可以用完全不同的内部实现
- `game_policy_models/*.py`
  - 负责 self-play replay、policy/value 训练、arena eval、artifact、推理
  - 不直接负责 collect orchestration

约束：

- `forge/data/game_gen.py` 不应该重新写死某个具体脚本路径
- collector 不应该自己判断某个 game 用 CFR、MCCFR、MCTS 还是 policy model
- `policy_model` 是额外采样后端，不是 exact teacher 的隐式替换

## Registry Contract

registry 返回的是显式的 `GameTrajectoryGeneratorSpec`：

```python
GameTrajectoryGeneratorSpec(
    name="leduc_poker_cfr",
    family="cfr",
    policy_path="artifacts/game_policies/leduc_poker/cfr/policy.pkl",
    policy_model_dir="artifacts/game_policy_models/leduc_poker/default",
    game_params={},
    default_iterations=200,
)
```

字段语义：

- `name`
  - 生成器逻辑名，用于日志与审计
- `family`
  - `mcts / minimax / cfr / mccfr / deep_cfr / policy_model / ...`
- `policy_path`
  - exact teacher snapshot 路径
- `policy_model_dir`
  - 训练好的小模型 artifact 目录
- `game_params`
  - 该游戏的 OpenSpiel 参数
- `default_iterations`
  - exact teacher 默认迭代数

当前默认实现是：

- `default`
  - 按 registry 走真实传统算法 family
- `policy_model`
  - 只对已经训练过小模型的游戏可用

## Generator Families

### Search

适用：

- `othello`
- `hex`
- `clobber`

特点：

- bounded-budget MCTS
- action-only 输出
- collect 时在线求解，但预算受控

### Exact Policy Snapshot

适用：

- `leduc_poker`
- `goofspiel`
- `liars_dice`
- `gin_rummy`

特点：

- collect 时不做在线 CFR/MCCFR 训练
- 只加载离线 snapshot
- 通过 exact teacher 产生高质量 expert action

### Policy Model

适用：

- 当前主要验证 `leduc_poker / goofspiel`
- 设计目标是后续覆盖 `liars_dice / gin_rummy`

特点：

- small per-game PyTorch policy/value model
- 输入是 structured state features
- 输出是 legal-action masked policy logits + value scalar
- 推理时默认 argmax
- action-only 输出，不引入 `<think>`

## Self-Play Route

当前训练路线是：

1. current best checkpoint root search
2. replay buffer build
3. PyTorch policy/value train
4. quick gate vs best
5. teacher gate vs exact baseline
6. `best` promotion

当前实现不是原版 AlphaZero 直接照搬，而是 AlphaZero-inspired：

- `goofspiel`
  - `turn-based conversion + custom PUCT`
- `leduc_poker / liars_dice / gin_rummy`
  - imperfect-information root search
  - `liars_dice` 在 OpenSpiel 缺少 `ResampleFromInfostate()` 时，不再依赖原生 `ISMCTSBot`
  - `gin_rummy` 在缺少 tensor observation 时，回退到 string-hash features

teacher 不再作为训练数据来源，只作为：

- baseline / arena 对手
- 最终晋级门槛
- 对比与回归验证

对应 CLI：

- `forge data game-selfplay-train --game <game>`
- `forge data game-selfplay-status --game <game>`
- `forge data game-selfplay-eval --game <game> --opponent teacher|best|checkpoint`
- `forge data game-selfplay-resume --game <game>`
- `forge data game-gen --game <game> --generator-source policy_model`
- `forge data game-build-policy --game <game>`

当前默认网络：

- `leduc_poker`
  - residual MLP, width `256`, blocks `3`
- `liars_dice`
  - residual MLP, width `256`, blocks `4`
- `goofspiel`
  - residual MLP, width `384`, blocks `4`
- `gin_rummy`
  - residual MLP, width `512`, blocks `6`, `LayerNorm`

## Rental Workflow

开发和调试阶段，当前不依赖 container。

当前标准化 rental 脚本：

- [rental_prepare_policy_env.sh](/home/wangtong/affine-swarm/scripts/game/rental_prepare_policy_env.sh)
- [rental_sync_policy_code.sh](/home/wangtong/affine-swarm/scripts/game/rental_sync_policy_code.sh)
- [rental_run_teacher_build.sh](/home/wangtong/affine-swarm/scripts/game/rental_run_teacher_build.sh)
- [rental_run_selfplay_train.sh](/home/wangtong/affine-swarm/scripts/game/rental_run_selfplay_train.sh)
- [rental_run_selfplay_eval.sh](/home/wangtong/affine-swarm/scripts/game/rental_run_selfplay_eval.sh)
- [rental_run_policy_sample_smoke.sh](/home/wangtong/affine-swarm/scripts/game/rental_run_policy_sample_smoke.sh)
- [targon_game_smoke.py](/home/wangtong/affine-swarm/scripts/game/targon_game_smoke.py)

当前脚本约定：

- 在 rental 上创建 `/root/affine-swarm/.venv`
- 用 tar-over-ssh 同步代码
- self-play train、teacher eval、policy sample 都走显式脚本
- 如果设置了 `HF_GAME_POLICY_REPO`，会把 `latest / best / arena / replay_meta / status` 持久化到私有 HF model repo
- 训练默认优先使用 GPU 上的 PyTorch

## TODO

下面这些是当前明确的后续工作，不要再从聊天记录里找：

1. `leduc_poker`
   - 把已验证通过的 `policy_model` 大规模采样接进正式 collect / ingest 路径
   - 增加 artifact 拉回、本地审查、和 HF publish 前的统计检查

2. `goofspiel`
   - 继续调 `policy_model` 路线，直到 rollout 能稳定保留 winning trajectories
   - 优先检查：
     - teacher/action label 是否足够覆盖
     - argmax 是否过于贪心
     - 是否需要更强的训练目标或更大 expert dataset
   - 在这条问题解决前，`goofspiel` 仍保留 exact teacher 路线作为主路径

3. `liars_dice / gin_rummy`
   - 完成 exact-parameter MCCFR teacher 的长期离线作业标准化
   - 让这些长作业具备：
     - 统一脚本入口
     - checkpoint / resume
     - 进度日志
   - 等 teacher artifact 可用后，再进入 expert dataset + policy model 训练阶段

4. Policy model evaluation
   - 不能只看 train accuracy
   - 必须新增 rollout-level 验证：
     - kept trajectory count
     - win rate after filtering
     - unique action-sequence coverage
     - per-game runtime / throughput

5. Sampling strategy
   - 后续评估是否需要：
     - argmax -> stochastic sampling
     - temperature / top-k
     - mixed generator strategy
   - 但在明确验证前，不要让 `policy_model` 静默替换 exact teacher

6. Documentation + progress tracking
   - 每次新增可用 game、完成大规模训练、或确认真实 blocker 后
   - 都要同步更新：
     - [docs/game-generators.md](/home/wangtong/affine-swarm/docs/game-generators.md)
     - [docs/refactor/progress.md](/home/wangtong/affine-swarm/docs/refactor/progress.md)

## 当前验证结论

截至当前：

- `leduc_poker`
  - real rental 上已完成：
    - exact teacher
    - expert dataset
    - PyTorch GPU training
    - `policy_model` sampling
  - 已经可以进入更大规模采样
- `goofspiel`
  - real rental 上已完成：
    - exact teacher
    - expert dataset
    - PyTorch GPU training
  - 但 `policy_model` sampling 仍是 blocker
- `liars_dice / gin_rummy`
  - 当前仍以 exact teacher 长作业为主
  - policy-model 路线还没进入可用采样阶段
