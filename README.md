# Affine Swarm

Affine Swarm 是一个围绕 Affine leaderboard 的数据、训练、评测和迭代优化工作台。

当前系统已经收口为：

- 控制层 `control plane`
- 执行层 `execution plane`
- 少量独立 sidecar

## 当前结构

```text
Control Plane
  Foundation
  Pipelines
  Agents
  forge/control + forge control

Execution Plane
  forge/execution + forge worker

Sidecars
  remote_ops
  monitoring
  domain_jobs
```

## 公开 CLI

统一入口：

```bash
forge --help
```

按安装方式暴露不同命令族：

- `uv pip install -e .`
  - 只安装共享核心
  - `forge --help` 只显示安装提示
- `uv pip install -e .[control]`
  - 暴露 `control`、`data`、`monitor`
- `uv pip install -e .[exec]`
  - 暴露 `worker`、`remote`
- `uv pip install -e .[all]`
  - 暴露全部命令族

## 快速开始

代码安装运行：

```bash
cp .env.example .env
uv pip install -e .[all]
forge --help
```

查看控制层：

```bash
forge control --help
```

查看执行层：

```bash
forge worker --help
```

查看数据命令：

```bash
forge data --help
```

控制层最小训练示例：

```bash
forge control create --id v1 --variable improve_game --hypothesis "more data helps" --train-config '{}' --data-config '{}'
forge control submit-train v1 tmp/game_train.jsonl --runtime targon --profile image --image wangtong123/affine-forge:latest --dataset-repo <repo> --gpu-type H200
```

执行层最小训练示例：

```bash
forge data aggregate --envs GAME -o tmp/game_train.jsonl --no-upload
forge worker render train tmp/game_train.jsonl --bundle-dir tmp/bundle-train
forge worker run tmp/bundle-train --runtime targon --profile bootstrap --dataset-repo <repo> --gpu-type H200
```

Docker 运行：

```bash
docker build -t wangtong123/affine-forge:latest .
docker run --rm -it --gpus all wangtong123/affine-forge:latest
```

## 数据合成入口

当前公开的数据合成入口是：

```bash
forge data navworld-gen -n 50 --type half_day -o data/navworld_half_day.jsonl
forge data liveweb-gen --seeds 1-100 --cache-dir /var/lib/liveweb-arena/cache -o data/liveweb_teacher.jsonl
forge data liveweb-gen --seeds 1-20 --cache-dir /var/lib/liveweb-arena/cache -m m1 --dry-run
forge data game-gen --all -n 2 -o data/game_random.jsonl
forge data memorygym-gen --seeds 10 --tier-mix -j 4 -o data/memorygym_raw.jsonl
forge data memorygym-split -i data/memorygym_raw.jsonl -o data/memorygym_split.jsonl --target 5000 --balance
forge data ingest data/memorygym_split.jsonl --env MEMORYGYM --source smoke
forge data canonical-upload --env MEMORYGYM
forge data publish-mixed --config mixed --split train
forge worker render collect --env NAVWORLD --bundle-dir tmp/bundle-collect -n 1
forge control submit-collect v1 --env NAVWORLD -n 1 --runtime targon --target <rental-machine> --profile rental --image wangtong123/affine-forge:latest --gpu-type H200
```

说明：

- `NAVWORLD` 保持现有 `forge data navworld-gen` 路径不变
- `GAME` 当前默认走随机轨迹生成器，collector 和 generator 已拆开
  - 生成器扩展方式见 [docs/game-generators.md](docs/game-generators.md)
- `LIVEWEB` 现在走 teacher-bot 合成器，依赖本地 `repos/liveweb-arena` 和缓存目录
- `MemoryGym` 现在分成两步：
  - `memorygym-gen` 生成 raw trajectories
  - `memorygym-split` 生成 canonical-ready event samples
- mixed 训练集会发布到 HF datasets repo 的 `mixed` config，可直接：
  - `load_dataset("waston10086/test_data", "mixed", split="train")`

## 文档结构

项目长期文档在 [`docs/`](docs/README.md)：

- [`docs/architecture-zh.md`](docs/architecture-zh.md)
- [`docs/cli.md`](docs/cli.md)
- [`docs/operations.md`](docs/operations.md)
- [`docs/testing.md`](docs/testing.md)
- [`docs/test-runbook.md`](docs/test-runbook.md)

重构治理文档在 [`docs/refactor/`](docs/refactor/README.md)：

- [`docs/refactor/roadmap.md`](docs/refactor/roadmap.md)
- [`docs/refactor/progress.md`](docs/refactor/progress.md)
- [`docs/refactor/real-test-plan.md`](docs/refactor/real-test-plan.md)
- [`docs/refactor/remediation-plan.md`](docs/refactor/remediation-plan.md)
- [`AGENTS.md`](AGENTS.md)

## 当前约定

- 项目文档负责说明“系统现在是什么、怎么用”
- 重构文档负责说明“这轮重构做到哪一步、怎么验证”
- 不再维护旧的 `forge train` / `forge eval` 文档和兼容说明
