# Cross-Machine Test Runbook

本文档用于在另一台机器上验证当前仓库是否能按预期安装、构建和运行。

默认目标：

- 验证安装矩阵是否符合设计
- 验证 `forge` CLI 是否按安装方式暴露正确命令
- 验证根目录 `Dockerfile` 是否可构建
- 验证控制层和执行层的最小 smoke 是否可跑

建议在全新目录、全新 Python 环境、无历史缓存前提下执行。

## 1. 前置准备

要求：

- Python `>=3.11`
- `uv`
- `git`
- `docker`

源码准备：

```bash
git clone <repo-url> affine-swarm
cd affine-swarm
```

如需跑训练相关测试，还需要安装 `affinetes` 源码：

```bash
git clone https://github.com/AffineFoundation/affinetes ../affinetes
uv pip install -e ../affinetes
```

环境文件：

```bash
cp .env.example .env
```

## 2. 安装矩阵测试

### 2.1 Shared Core

```bash
uv venv .venv-core
uv pip install --python .venv-core/bin/python -e .
.venv-core/bin/forge --help
```

通过标准：

- `forge --help` 能运行
- 不显示 `control`
- 不显示 `data`
- 不显示 `monitor`
- 不显示 `worker`
- 不显示 `remote`
- help 里包含安装提示：
  - `uv pip install -e .[control]`
  - `uv pip install -e .[exec]`
  - `uv pip install -e .[all]`

### 2.2 Control Plane Install

```bash
uv venv .venv-control
uv pip install --python .venv-control/bin/python -e .[control]
.venv-control/bin/forge --help
.venv-control/bin/forge control --help
.venv-control/bin/forge data --help
.venv-control/bin/forge monitor --help
```

通过标准：

- `forge --help` 显示：
  - `control`
  - `data`
  - `monitor`
- `forge --help` 不显示：
  - `worker`
  - `remote`

### 2.3 Execution Plane Install

```bash
uv venv .venv-exec
uv pip install --python .venv-exec/bin/python -e .[exec]
.venv-exec/bin/forge --help
.venv-exec/bin/forge worker --help
.venv-exec/bin/forge remote --help
```

通过标准：

- `forge --help` 显示：
  - `worker`
  - `remote`
- `forge --help` 不显示：
  - `control`
  - `data`
  - `monitor`

### 2.4 Full Install

```bash
uv venv .venv-all
uv pip install --python .venv-all/bin/python -e .[all]
.venv-all/bin/forge --help
```

通过标准：

- `forge --help` 显示全部命令族：
  - `control`
  - `data`
  - `monitor`
  - `worker`
  - `remote`

## 3. 本地代码测试

在完整环境下执行：

```bash
uv pip install --python .venv-all/bin/python -e ../affinetes
.venv-all/bin/python -m pytest -q
```

通过标准：

- 全量 pytest 通过

如果只想先跑核心回归：

```bash
.venv-all/bin/python -m pytest -q tests/test_cli.py tests/test_control.py tests/test_execution.py tests/test_agent.py tests/test_compute.py tests/test_training.py
```

## 4. Control Plane 本地 smoke

在 `.[control]` 或 `.[all]` 环境下执行：

```bash
mkdir -p tmp/runbook
printf '{"messages":[]}\n' > tmp/runbook/train.jsonl

.venv-control/bin/forge control create \
  --id runbook-v1 \
  --variable install_matrix \
  --hypothesis "control-only install can manage remote image runs" \
  --train-config '{"model":"Qwen/Qwen2.5-0.5B-Instruct","learning_rate":0.0001,"lora_rank":64,"max_length":1024,"num_train_epochs":1,"output_dir":"/tmp/checkpoints"}' \
  --data-config '{"GAME":{"count":1}}'

.venv-control/bin/forge control render-train runbook-v1 tmp/runbook/train.jsonl --bundle-dir tmp/runbook/bundle-train
.venv-control/bin/forge control show runbook-v1 --json
```

通过标准：

- experiment 创建成功
- `render-train` 成功
- bundle 目录存在
- experiment JSON 中记录了 `training_run.bundle_path`

## 5. Execution Plane 本地 smoke

在 `.[exec]` 或 `.[all]` 环境下执行：

```bash
mkdir -p tmp/runbook
printf '{"messages":[]}\n' > tmp/runbook/train.jsonl

.venv-exec/bin/forge worker render train tmp/runbook/train.jsonl --bundle-dir tmp/runbook/bundle-train --job-id runbook-train
.venv-exec/bin/forge worker validate-bundle tmp/runbook/bundle-train
```

通过标准：

- bundle 渲染成功
- `validate-bundle` 通过
- bundle 内至少存在：
  - `job.json`
  - `scripts/entrypoint.sh`
  - `inputs/swift_config.yaml`

## 6. Docker Build 测试

在仓库根目录执行：

```bash
docker build -t affine-forge:test .
docker run --rm affine-forge:test bash -lc 'python --version && swift --help >/dev/null'
```

通过标准：

- 根目录 `Dockerfile` 可成功 build
- 容器能成功启动
- 容器里能找到 `swift`

## 7. Worker Docker Runtime Smoke

在 `.[exec]` 或 `.[all]` 环境下执行：

```bash
.venv-exec/bin/forge worker run tmp/runbook/bundle-train --runtime docker --foreground --image affine-forge:test
.venv-exec/bin/forge worker status tmp/runbook/bundle-train
.venv-exec/bin/forge worker logs tmp/runbook/bundle-train --tail 50
.venv-exec/bin/forge worker collect tmp/runbook/bundle-train
```

通过标准：

- `run` 成功
- `status` 可读
- `logs` 可读
- `collect` 成功

## 8. Remote Docker Build Command

如果目标机器已安装 Docker 且已注册：

```bash
.venv-exec/bin/forge remote machine -m <machine> docker-build affine-forge:test
```

通过标准：

- 命令成功
- 使用的是仓库根目录 `Dockerfile`

## 9. 可选的远程真实 smoke

### 9.1 Control-only Remote Image Smoke

```bash
.venv-control/bin/forge control submit-train runbook-v1 tmp/runbook/train.jsonl \
  --runtime targon \
  --target <rental-machine> \
  --profile rental \
  --image wangtong123/affine-forge:latest \
  --gpu-type H200
```

后续：

```bash
.venv-control/bin/forge control run-status runbook-v1
.venv-control/bin/forge control run-logs runbook-v1 --tail 80
.venv-control/bin/forge control terminate-run runbook-v1
```

通过标准：

- 能拿到真实 `run_id`
- 后续命令不需要重复传 `--runtime`
- 可读取状态和日志
- 未配置 `HF_RUNTIME_REPO` / `HF_TOKEN` 时仍可启动；此时 bundle 会通过 SSH 上传到 rental 机器

### 9.2 Exec-only Remote Image Smoke

```bash
.venv-exec/bin/forge worker run tmp/runbook/bundle-train \
  --runtime targon \
  --target <rental-machine> \
  --profile rental \
  --foreground \
  --image wangtong123/affine-forge:latest \
  --gpu-type H200
```

后续：

```bash
.venv-exec/bin/forge worker status tmp/runbook/bundle-train
.venv-exec/bin/forge worker logs tmp/runbook/bundle-train --tail 80
.venv-exec/bin/forge worker terminate tmp/runbook/bundle-train
```

通过标准：

- bundle 可提交到远程 image runtime
- `--foreground` 会等待远端容器退出并返回实际退出状态
- `status/logs/terminate` 可用

## 10. 结果记录模板

建议至少记录：

- 机器名 / 操作系统 / Python 版本
- uv 版本
- Docker 版本
- 使用了哪种安装方式：`.` / `.[control]` / `.[exec]` / `.[all]`
- 是否安装了 `affinetes`
- 哪些步骤通过
- 哪些步骤失败
- 失败日志路径
- 如涉及远程执行，记录 `run_id`
