# Operations Guide

本文档只记录当前还在使用的运行与运维规则。

## 1. 运行环境分层

当前环境分三类：

- 本地开发
  - 用于代码调试、bundle 渲染、最小 smoke test
- 执行层 runtime
  - `docker`
  - `ssh`
  - `targon`
- Sidecar 运维
  - `forge remote`
  - `forge monitor`

## 2. Targon 运行模式

Targon 是当前最重要的生产 runtime。

支持两个显式 profile：

- `bootstrap`
- `image`

### `bootstrap`

适合从基础镜像启动，在容器内补装依赖。

```bash
uv run forge worker run tmp/bundle-train \
  --runtime targon \
  --profile bootstrap \
  --dataset-repo <repo> \
  --gpu-type H200
```

### `image`

适合使用已经构建好的执行镜像。

```bash
uv run forge worker run tmp/bundle-train \
  --runtime targon \
  --profile image \
  --image wangtong123/affine-forge:latest \
  --dataset-repo <repo> \
  --gpu-type H200
```

规则：

- profile 必须显式指定
- 不做自动 fallback
- bundle staging、日志抓取、artifact 回收属于 runtime 自己的责任

## 3. 远程机器

SSH 机器通过 `forge remote machine` 管理。

注册示例：

```bash
uv run forge remote machine register test-box <host> \
  --port 22 \
  --user root \
  --key ~/.ssh/affine_rental \
  --gpu-type H200
```

查看状态：

```bash
uv run forge remote machine -m test-box status
```

## 4. 真实验证的机器规则

当任务涉及真实 runtime 验证时：

- 不默认复用 `machines.json`
- 不复用正在跑无关任务的机器
- Targon rental / SSH 验证应优先起新的隔离机器
- 验证完成后及时终止，避免继续占资源

## 5. 开发与部署镜像

当前约定是：

- 开发期优先使用现成基础镜像做 bundle smoke
- 流程稳定后再固化成 Dockerfile 和部署镜像

也就是说：

- “探索环境” 是开发流程
- “固定 Dockerfile / 固定镜像” 是部署流程

不要在依赖和启动顺序还没跑稳时，过早把探索过程写死成正式镜像。

## 6. 日志与产物

查看运行日志：

```bash
uv run forge worker logs tmp/bundle-train --tail 80
uv run forge control run-logs <exp-id> --task train --tail 80
```

收集产物：

```bash
uv run forge worker collect tmp/bundle-train
uv run forge control collect-run <exp-id> --task train
```

真实测试报告统一写到：

- `logs/real-tests/YYYY-MM-DD/`

## 7. 常见选择

- 想单独调试 runtime：用 `forge worker`
- 想按 experiment 跟踪任务：用 `forge control`
- 想查容量、租机、注册机器：用 `forge remote`
- 想做正式真实验证：先看 [`refactor/real-test-plan.md`](refactor/real-test-plan.md)
