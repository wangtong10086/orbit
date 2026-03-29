# CLI Guide

当前公开 CLI 只有五个家族：

- `data`
- `control`
- `worker`
- `remote`
- `monitor`

统一入口：

```bash
uv sync
uv run forge --help
```

## 1. `data`

用途：

- 数据校验
- canonical ingest
- 本地训练数据构建
- NAVWORLD 合成数据生成

常用命令：

```bash
uv run forge data validate tmp/navworld.jsonl --env NAVWORLD
uv run forge data ingest tmp/navworld.jsonl --env NAVWORLD --source smoke
uv run forge data aggregate --envs GAME,NAVWORLD -o tmp/train.jsonl --no-upload
uv run forge data navworld-gen -n 2 --type half_day -o tmp/navworld.jsonl
```

## 2. `control`

用途：

- 管理 experiment
- 提交 train / eval / collect 到执行层
- 查询运行状态
- 读取日志
- 收集产物

常用命令：

```bash
uv run forge control list
uv run forge control show <exp-id> --json
uv run forge control create --id v1 --variable improve_game --hypothesis "more data helps" --train-config '{}' --data-config '{}'
uv run forge control submit-train <exp-id> tmp/train.jsonl --runtime targon --profile bootstrap --dataset-repo <repo> --gpu-type H200
uv run forge control submit-eval <exp-id> --model Qwen/Qwen2.5-0.5B-Instruct --envs GAME --runtime targon --profile bootstrap --dataset-repo <repo> --gpu-type H200
uv run forge control submit-collect-navworld <exp-id> -n 1 --runtime targon --profile bootstrap --dataset-repo <repo> --gpu-type H200
uv run forge control run-status <exp-id> --task train
uv run forge control run-logs <exp-id> --task eval --tail 80
uv run forge control collect-run <exp-id> --task collect
uv run forge control terminate-run <exp-id> --task train
```

说明：

- `control` 是高层控制面
- follow-up 命令依赖 experiment 中记录的 run handle，不需要重复传 `--runtime`

## 3. `worker`

用途：

- 渲染 bundle
- 校验 bundle
- 直接通过执行层运行 bundle
- 绕过控制层做独立调试

常用命令：

```bash
uv run forge worker render train tmp/train.jsonl --bundle-dir tmp/bundle-train
uv run forge worker render eval --bundle-dir tmp/bundle-eval --model Qwen/Qwen3-32B-TEE --envs GAME --samples 1 --base-url https://llm.chutes.ai/v1
uv run forge worker render collect-navworld --bundle-dir tmp/bundle-collect -n 1
uv run forge worker validate-bundle tmp/bundle-train
uv run forge worker run tmp/bundle-train --runtime targon --profile bootstrap --dataset-repo <repo> --gpu-type H200
uv run forge worker status tmp/bundle-train
uv run forge worker logs tmp/bundle-train --tail 80
uv run forge worker collect tmp/bundle-train
uv run forge worker terminate tmp/bundle-train
```

说明：

- `worker` 是执行层入口
- 适合开发、排障、真实 runtime smoke test

## 4. `remote`

用途：

- 查看 Targon 容量
- 注册/管理远程机器
- 镜像和远程环境操作

常用命令：

```bash
uv run forge remote compute capacity
uv run forge remote compute list
uv run forge remote machine --help
uv run forge remote machine register <name> <host> --user root --key ~/.ssh/id_rsa
uv run forge remote machine -m <name> status
```

## 5. `monitor`

用途：

- 监控 leaderboard、实验外部状态和相关观测信息

```bash
uv run forge monitor --help
```

## 6. 使用建议

- 想直接运行 bundle：用 `worker`
- 想按 experiment 管理任务：用 `control`
- 想做远程机器和 Targon 运维：用 `remote`
- 旧的 `forge train` / `forge eval` 已删除，不再是当前 API
