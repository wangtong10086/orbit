# GAME Generators

`GAME` 数据收集现在把“collector”和“trajectory generator”拆开了。

目的：

- 让 `forge data game-gen` / `forge worker render collect --env GAME` 保持稳定
- 让不同游戏可以逐步切回更强的真实生成器
- 避免再次把所有游戏硬绑到同一条生成脚本上

## 当前状态

当前默认策略是：

- 所有 7 个游戏都通过统一的 generator registry 选择生成器
- 当前 registry 默认返回 `random` 生成器
- 随机生成器脚本是 [generate_random.py](/home/wangtong/affine-swarm/scripts/game/generate_random.py)

当前 7 个游戏：

- `goofspiel`
- `leduc_poker`
- `liars_dice`
- `gin_rummy`
- `othello`
- `hex`
- `clobber`

这条默认路径的目标是“先稳定收集轨迹”，不是“先追求最强策略质量”。

## 模块边界

核心文件：

- Registry: [game_trajectory_generators.py](/home/wangtong/affine-swarm/forge/data/game_trajectory_generators.py)
- Collector glue: [game_gen.py](/home/wangtong/affine-swarm/forge/data/game_gen.py)
- Current default generator: [generate_random.py](/home/wangtong/affine-swarm/scripts/game/generate_random.py)

职责分工：

- `game_gen.py`
  - 负责 collector 级调度
  - 负责 oversampling、seed 批次、按游戏拼接 staging 文件
  - 不负责具体对局策略
- `game_trajectory_generators.py`
  - 负责“某个游戏当前应该用哪个生成器”
  - 返回显式 `GameTrajectoryGeneratorSpec`
- `scripts/game/*.py`
  - 负责真实对局轨迹生成
  - 每个脚本可以有自己的 bot / MCTS / rule / model 路径

约束：

- `forge/data/game_gen.py` 不应该重新写死某个具体脚本路径
- 新生成器必须通过 registry 接入
- collector 不应该知道某个 game 是随机、rule、MCTS 还是模型生成

## Registry Contract

registry 返回的是：

```python
GameTrajectoryGeneratorSpec(
    name="random",
    script_path=".../scripts/game/generate_random.py",
    env={},
)
```

字段语义：

- `name`
  - 生成器名字，只用于可读性和后续审计
- `script_path`
  - 实际执行的脚本路径
- `env`
  - 仅该生成器需要的附加环境变量

当前默认实现是：

- 不区分 game
- 所有 game 都返回 `random`

## 生成器脚本约定

当前 collector 通过下面的调用协议执行生成器：

```bash
python <script> --game <game> -n <batch> --start-seed <seed> -o <output>
```

脚本需要满足：

1. 支持 `--game`
2. 支持 `-n`
3. 支持 `--start-seed`
4. 支持 `-o/--output`
5. 输出 JSONL，每行一条 canonical-ready `GAME` 记录
6. 允许“部分 win / 部分 loss”
7. 对于 loss，可直接不写入输出文件
8. 退出码非 0 时视为 collector 失败

输出记录的最小要求：

- `messages`
- `env="GAME"`
- `game`
- `score`
- `task_id`
- `seed`

## 当前默认随机生成器

[generate_random.py](/home/wangtong/affine-swarm/scripts/game/generate_random.py) 的行为：

- 双方都用随机策略
- bot 侧只记录自身回合的 `user/assistant` 轨迹
- assistant 输出只保留 action id
- 只保留 `score >= 0.5` 的轨迹

优点：

- 快
- 稳
- 7 个游戏都能产数

限制：

- 轨迹质量只保证“可收集”和“格式正确”
- 不代表最终最优训练数据

## 之后如何接回更强生成器

推荐按游戏逐个恢复，不要一次性切全量。

步骤：

1. 新增或确定某个真实生成脚本
   - 例如 `generate_rule_think.py`
   - 或未来的 `generate_mcts.py`
   - 或 `generate_model_distill.py`
2. 在 [game_trajectory_generators.py](/home/wangtong/affine-swarm/forge/data/game_trajectory_generators.py) 里给目标 game 返回新的 `GameTrajectoryGeneratorSpec`
3. 保持脚本 CLI 协议不变
4. 跑单游戏真实 probe
5. 再跑 `all-games` collect

推荐恢复顺序：

1. 单个游戏 probe
2. 单个游戏 collect bundle
3. `--all-games` collect

不要直接：

- 同时恢复多个高复杂度生成器
- 绕过 registry 在 `game_gen.py` 里写条件分支
- 把 collector 逻辑和具体 bot/MCTS 逻辑重新混在一起

## 开发建议

如果后面要支持多种 generator 模式，推荐把 registry 扩成显式按 game 返回：

```python
if game_name == "gin_rummy":
    return GameTrajectoryGeneratorSpec(
        name="rule_think",
        script_path=".../scripts/game/generate_rule_think.py",
    )
```

如果某个生成器需要特殊环境变量，也只放进 `env`：

```python
return GameTrajectoryGeneratorSpec(
    name="model_distill",
    script_path=".../scripts/game/generate_model_distill.py",
    env={"OPENAI_API_KEY": "..."},
)
```

不要把这类配置直接散落回 `game_gen.py`。

## 当前验证结论

当前默认 `random` generator 已经通过真实 collect 验证：

- 7 个游戏都能产数
- `forge worker render collect --env GAME --all-games ...` 能完成 ingest + mixed publish
- mixed 数据集可继续通过 `load_dataset(...)` 读取
