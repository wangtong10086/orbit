# CLI Guide

统一入口是 `forge`，但命令族取决于安装方式：

```bash
uv pip install -e .[control]
forge --help
```

安装矩阵：

- `uv pip install -e .`
  - 共享核心 only
- `uv pip install -e .[control]`
  - `control`
  - `data`
  - `monitor`
- `uv pip install -e .[exec]`
  - `worker`
  - `remote`
- `uv pip install -e .[all]`
  - 全部命令族

## 1. `data` and `control`

用途：

- 数据校验
- canonical ingest
- 本地训练数据构建
- NAVWORLD 合成数据生成
- experiment 管理
- 提交 train / eval / collect 到远程执行镜像
- 查询运行状态、日志和产物

常用命令：

```bash
forge data validate tmp/navworld.jsonl --env NAVWORLD
forge data ingest tmp/navworld.jsonl --env NAVWORLD --source smoke
forge data aggregate --envs GAME,NAVWORLD -o tmp/train.jsonl --no-upload
forge data navworld-gen -n 2 --type half_day -o tmp/navworld.jsonl
forge control list
forge control show <exp-id> --json
forge control create --id v1 --variable improve_game --hypothesis "more data helps" --train-config '{}' --data-config '{}'
forge control submit-train <exp-id> tmp/train.jsonl --runtime targon --target <rental-machine> --profile rental --image wangtong123/affine-forge:latest --gpu-type H200
forge control submit-eval <exp-id> --model Qwen/Qwen2.5-0.5B-Instruct --envs GAME --runtime targon --target <rental-machine> --profile rental --image wangtong123/affine-forge:latest --gpu-type H200
forge control submit-collect-navworld <exp-id> -n 1 --runtime targon --target <rental-machine> --profile rental --image wangtong123/affine-forge:latest --gpu-type H200
forge control run-status <exp-id> --task train
forge control run-logs <exp-id> --task eval --tail 80
forge control collect-run <exp-id> --task collect
forge control terminate-run <exp-id> --task train
```

说明：

- `control` 是高层控制面
- `.[control]` 下默认走远程 `targon + rental`
- rental 目标不要求预先配置 `HF_RUNTIME_REPO` / `HF_TOKEN`；有配置时会优先走 HF staging，没有则回退到 SSH 上传 bundle
- follow-up 命令依赖 experiment 中记录的 run handle，不需要重复传 `--runtime`

## 2. `worker` and `remote`

用途：

- 渲染 bundle
- 校验 bundle
- 直接通过执行层运行 bundle
- 绕过控制层做独立调试

常用命令：

```bash
forge worker render train tmp/train.jsonl --bundle-dir tmp/bundle-train
forge worker render eval --bundle-dir tmp/bundle-eval --model Qwen/Qwen3-32B-TEE --envs GAME --samples 1 --base-url https://llm.chutes.ai/v1
forge worker render collect-navworld --bundle-dir tmp/bundle-collect -n 1
forge worker validate-bundle tmp/bundle-train
forge worker run tmp/bundle-train --runtime targon --target <rental-machine> --profile rental --image wangtong123/affine-forge:latest --gpu-type H200
forge worker run tmp/bundle-train --runtime targon --target <rental-machine> --profile rental --foreground --image wangtong123/affine-forge:latest --gpu-type H200
forge worker status tmp/bundle-train
forge worker logs tmp/bundle-train --tail 80
forge worker collect tmp/bundle-train
forge worker terminate tmp/bundle-train
forge remote machine --help
forge remote machine register <name> <host> --user root --key ~/.ssh/id_rsa
forge remote machine -m <name> status
```

说明：

- `worker` 是执行层入口
- `remote` 是执行层运维入口
- `.[exec]` 提供本地 replay、远程 runtime 和镜像构建
- `worker run --runtime targon --foreground` 会等待远端容器退出，而不是立即返回
- `remote machine docker-build` 只有在 `HTTP_PROXY` / `HTTPS_PROXY` 指向 `localhost` 或 `127.0.0.1` 时才会自动加 `--network host`

## 3. `monitor`

```bash
forge monitor --help
```

## 4. 使用建议

- 想按 experiment 管理远程镜像任务：装 `.[control]`
- 想直接运行 bundle 或做 runtime 调试：装 `.[exec]`
- 想做完整开发和回归：装 `.[all]`
- 旧的 `forge train` / `forge eval` 已删除，不再是当前 API
