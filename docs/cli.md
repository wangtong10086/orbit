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
- HF datasets sync / mixed publish
- 本地训练数据构建
- NAVWORLD 合成数据生成
- LIVEWEB teacher-bot 合成
- MEMORYGYM raw 生成与 event split
- experiment 管理
- 提交 train / eval / collect 到远程执行镜像
- 查询运行状态、日志和产物

常用命令：

```bash
forge data validate tmp/navworld.jsonl --env NAVWORLD
forge data ingest tmp/navworld.jsonl --env NAVWORLD --source smoke
forge data aggregate --envs GAME,NAVWORLD -o tmp/train.jsonl --no-upload
forge data game-gen --all -n 2 -o tmp/game.jsonl
forge data game-build-policy --game leduc_poker
forge data game-upload-teacher --game leduc_poker --repo <private-model-repo>
forge data game-selfplay-train --game leduc_poker --episodes 128 --repo <private-model-repo>
forge data game-selfplay-status
forge data game-selfplay-eval --game leduc_poker --opponent teacher --games 200
forge data game-selfplay-resume --game liars_dice --repo <private-model-repo>
forge data game-policy-status
forge data game-policy-model-status
forge data game-gen --game leduc_poker --generator-source policy_model -n 20 -o tmp/game_leduc_policy.jsonl
forge data navworld-gen -n 2 --type half_day -o tmp/navworld.jsonl
forge data liveweb-gen --seeds 1-100 --cache-dir /var/lib/liveweb-arena/cache -o tmp/liveweb.jsonl
forge data liveweb-gen --seeds 1-10 --cache-dir /var/lib/liveweb-arena/cache -m m1 --dry-run
forge data memorygym-gen --seeds 10 --tier-mix -j 4 -o tmp/memorygym_raw.jsonl
forge data memorygym-split -i tmp/memorygym_raw.jsonl -o tmp/memorygym.jsonl --target 5000 --balance
forge data ingest tmp/memorygym.jsonl --env MEMORYGYM --source smoke
forge data canonical-upload --env MEMORYGYM
forge data canonical-sync --env NAVWORLD
forge data publish-mixed --config mixed --split train
forge control list
forge control show <exp-id> --json
forge control create --id v1 --variable improve_game --hypothesis "more data helps" --train-config '{}' --data-config '{}'
forge control submit-train <exp-id> tmp/train.jsonl --runtime targon --target <rental-machine> --profile rental --image wangtong123/affine-forge:latest --gpu-type H200
forge control submit-eval <exp-id> --model Qwen/Qwen2.5-0.5B-Instruct --envs GAME --runtime targon --target <rental-machine> --profile rental --image wangtong123/affine-forge:latest --gpu-type H200
forge control submit-collect <exp-id> --env NAVWORLD -n 1 --runtime targon --target <rental-machine> --profile rental --image wangtong123/affine-forge:latest --gpu-type H200
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
- `game-gen` 现在按 game registry 选择传统算法 generator
  - `othello / hex / clobber` 走 search generator
  - `goofspiel / leduc_poker / liars_dice / gin_rummy` 走 offline policy snapshot generator
  - policy 类游戏需要先用 `game-build-policy` 产出 snapshot
  - `--generator-source policy_model` 会改用 self-play 训练出的 policy/value checkpoint
- `game-upload-teacher` 会把 exact teacher snapshot 上传到私有 HF model repo
  - 默认读取 `HF_GAME_TEACHER_REPO`
  - 上传 `policy.pkl + metadata.json + README.md`
- `game-selfplay-train` 是当前主训练入口
  - 走 AlphaZero-inspired `root search -> replay -> policy/value train -> arena eval`
  - 默认优先使用 `cuda`
  - 如果配置了 `HF_GAME_POLICY_REPO`，会把 `latest/best/status/arena/replay_meta` 持久化到私有 HF model repo
- `game-selfplay-status` 查看 `latest / best / arena / pass_streak`
- `game-selfplay-eval` 显式对战 `teacher / best / checkpoint`
- `game-selfplay-resume` 会先尝试从私有 HF repo 恢复 checkpoint 再继续训练
- `game-policy-model-status` 用来确认 `model.pt + metadata.json` 是否已就绪
  - generator 架构和扩展方式见 [game-generators.md](/home/wangtong/affine-swarm/docs/game-generators.md)
- `liveweb-gen` 依赖 `repos/liveweb-arena` 和有效的 cache dir；`--machine` 走当前的 `forge remote machine exec` 路径
- `memorygym-gen` 依赖 `repos/MemoryGym`
- `memorygym-split` 产出的文件是 canonical-ready staging 文件；需要再用 `forge data ingest --env MEMORYGYM` 写入 canonical
- `publish-mixed` 会从 canonical 构建 HF Dataset Viewer 友好的 mixed config，可通过 `load_dataset("waston10086/test_data", "mixed", split="train")` 使用

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
forge worker render collect --env NAVWORLD --bundle-dir tmp/bundle-collect -n 1
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
forge remote targon inventory --type serverless
forge remote targon apps
forge remote targon api GET /tha/v2/workloads
forge remote targon cli inventory
```

说明：

- `worker` 是执行层入口
- `remote` 是执行层运维入口
- `.[exec]` 提供本地 replay、远程 runtime 和镜像构建
- `worker run --runtime targon --foreground` 会等待远端容器退出，而不是立即返回
- collect bundle 在远端镜像内会执行 `采集 -> canonical 更新 -> mixed dataset 发布 -> HF 上传`
- `remote machine docker-build` 只有在 `HTTP_PROXY` / `HTTPS_PROXY` 指向 `localhost` 或 `127.0.0.1` 时才会自动加 `--network host`
- `remote targon ...` 是开发 / 调试 sidecar，用于直接调 Targon API / CLI，不是正式执行入口
- `GAME` policy-model 开发期当前以 rental + 脚本为主，不依赖 container

## 3. `monitor`

```bash
forge monitor --help
```

## 4. 使用建议

- 想按 experiment 管理远程镜像任务：装 `.[control]`
- 想直接运行 bundle 或做 runtime 调试：装 `.[exec]`
- 想做完整开发和回归：装 `.[all]`
- 旧的 `forge train` / `forge eval` 已删除，不再是当前 API
