# Operations Guide

本文档只记录当前还在使用的运行与运维规则。

## 1. 运行环境分层

当前环境分三类：

- 本地开发
  - 用于代码调试、bundle 渲染、最小 smoke test
- 执行层 runtime
  - `docker`
  - `ssh`
  - `targon rental`
- Sidecar 运维
  - `forge remote`
  - `forge monitor`
  - `forge remote targon` for direct Targon API / CLI debugging

## 2. 安装方式

常用安装矩阵：

- 控制层：
  - `uv pip install -e .[control]`
- 执行层：
  - `uv pip install -e .[exec]`
- 完整开发环境：
  - `uv pip install -e .[all]`

控制层安装默认通过远程 Targon rental 机器上的执行镜像提交任务，不提供本地 `worker` replay。

## 3. Targon rental 运行模式

Targon 是当前最重要的生产 runtime，但现在只使用 rental 机器路径，不再使用 serverless container 路径。

当前只保留一个显式 profile：

- `rental`

执行方式是：

- 通过 `machines.json` 中注册的 SSH rental 机器定位目标
- 优先使用 HF staging 传递 project/bundle；如果未配置 `HF_RUNTIME_REPO` + `HF_TOKEN`，则自动回退到 SSH 上传
- 在租赁机上 `docker pull` Docker Hub 镜像
- 在租赁机上 `docker run` 执行任务

```bash
forge worker run tmp/bundle-train \
  --runtime targon \
  --target <rental-machine> \
  --profile rental \
  --foreground \
  --image wangtong123/affine-forge:latest \
  --gpu-type H200
```

规则：

- `--target` 必须显式指定
- profile 必须显式指定为 `rental`
- 不做 runtime/profile 自动 fallback
- 不再通过 serverless workload 传 bundle
- `HF_RUNTIME_REPO` 和 `HF_TOKEN` 不是启动 rental 的前置条件；配置后只会影响 staging 方式
- bundle staging、日志抓取、artifact 回收都由 rental runtime 自己负责
- `--foreground` 在 `targon rental` 下会阻塞直到远端容器退出；默认仍是 detach 模式

## 3.1 Targon 直连调试模式

为了开发和调试方便，允许通过 `remote_ops` sidecar 直接使用 Targon API 和 CLI。

这条路径只用于：

- 查容量
- 调试 app / workload / logs
- 在 SDK 或 runtime 抽象不够用时排查问题
- 辅助租机、注册、定位原始平台错误

这条路径不用于：

- 取代 `forge worker run ... --runtime targon`
- 取代 `forge control submit-* --runtime targon`
- 在 train / eval / collect 主路径里偷偷回退成平台直连

示例：

```bash
forge remote targon inventory --type serverless
forge remote targon apps
forge remote targon api GET /tha/v2/workloads
forge remote targon cli inventory
forge remote targon cli logs <workload-id>
```

## 4. 远程机器

SSH 机器通过 `forge remote machine` 管理。

注册示例：

```bash
forge remote machine register test-box <host> \
  --port 22 \
  --user root \
  --key ~/.ssh/affine_rental \
  --gpu-type H200
```

查看状态：

```bash
forge remote machine -m test-box status
```

## 5. Docker 镜像入口

当前唯一活跃的执行镜像构建入口在仓库根目录：

```bash
docker build -t wangtong123/affine-forge:latest .
```

`forge remote machine docker-build` 也默认使用根目录 `Dockerfile`。

如果本机配置了代理：

- 会把 `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` 传给 `docker build`
- 只有当 `HTTP_PROXY` 或 `HTTPS_PROXY` 指向 `localhost` / `127.0.0.1` 时，才会自动加 `--network host`
- 仅凭 `NO_PROXY=localhost,127.0.0.1,...` 不会触发 `--network host`

## 6. 真实验证的机器规则

当任务涉及真实 runtime 验证时：

- 不默认复用 `machines.json`
- 不复用正在跑无关任务的机器
- Targon rental / SSH 验证应优先起新的隔离机器
- 验证完成后及时终止，避免继续占资源

## 7. 开发与部署镜像

当前约定是：

- 开发期优先使用现成基础镜像做 bundle smoke
- 当前已经固定为根目录 `Dockerfile` 和执行镜像

也就是说：

- “探索环境” 是开发流程
- “根目录 Dockerfile / 固定镜像” 是部署流程

不要在依赖和启动顺序还没跑稳时，过早把探索过程写死成正式镜像。

## 8. 日志与产物

查看运行日志：

```bash
forge worker logs tmp/bundle-train --tail 80
forge control run-logs <exp-id> --task train --tail 80
```

收集产物：

```bash
forge worker collect tmp/bundle-train
forge control collect-run <exp-id> --task train
```

真实测试报告统一写到：

- `logs/real-tests/YYYY-MM-DD/`

## 9. 常见选择

- 想单独调试 runtime：用 `forge worker`
- 想按 experiment 跟踪任务：用 `forge control`
- 想查容量、租机、注册机器：用 `forge remote`
- 想做正式真实验证：先看 [`refactor/real-test-plan.md`](refactor/real-test-plan.md)
