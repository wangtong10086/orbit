# Refactor Roadmap

**Status:** Active

## 重构目标

Affine Swarm 的系统级目标从“只有三层主干”调整为：

- **控制层**：负责定义任务、发起任务、追踪状态、读取结果、做高层编排与决策
- **执行层**：负责真正执行 `train / eval / collect` 任务，运行在 Docker、SSH、Targon 或其他 GPU 运行环境上

控制层内部仍然保留三层主干：

- Layer 0 — Foundation
- Layer 1 — Pipelines
- Layer 2 — Agents

执行层是系统级独立平面，不属于三层主干内部模块。

## 当前阶段目标

当前进入**执行层落地后，控制层开始重建**的阶段。

本阶段要达到的状态是：

- 执行层拥有独立包 `forge/execution/`
- 执行层拥有独立 CLI 家族 `forge worker`
- 执行层可通过 `job file / bundle + runtime backend` 独立运行
- 执行层能手工完成 `train / eval / collect`
- 只保留新的 `forge worker` 与 `forge control` 公开入口，不保留兼容
- 控制层开始通过独立包 `forge/control/` 管理实验与高层任务
- 控制层开始通过 `forge control` 作为新的公开控制面 CLI

## 长期目标架构

### 控制层

控制层长期保留三层主干：

- `Foundation`
  - 稳定 contracts、catalog、repository、scoring 等
- `Pipelines`
  - 实验、数据、训练、评测编排
- `Agents`
  - 高层策略与任务编排

控制层职责：

- 定义任务意图
- 生成 job request
- 调度执行层
- 查询运行状态
- 汇总 artifacts 和评测结果
- 决策下一步动作

### 执行层

执行层独立负责真实任务执行。

核心构成：

- `JobSpec`
- `TaskSpec`
  - `TrainTaskSpec`
  - `EvalTaskSpec`
  - `CollectTaskSpec`
- `JobBundle`
- `RuntimeBackend`
- `RunHandle`
- `RunStatus`
- `ArtifactManifest`

执行层职责：

- 将任务 bundle 物化为本地可审计目录
- 准备运行 workspace
- 启动任务
- 查询状态
- 拉取日志
- 收集 artifacts

## 核心边界规则

### 1. 任务渲染与运行时彻底分离

任务渲染器只负责生成 bundle，不负责平台执行。

允许：

- 生成 `swift_config.yaml`
- 生成 `entrypoint.sh`
- 复制输入文件
- 描述预期输出

禁止：

- 在 renderer 中处理 Targon workload name
- 在 renderer 中处理 HF 上传
- 在 renderer 中处理 SSH 上传
- 在 renderer 中处理 screen / serverless / 容器启动细节

### 2. Targon / SSH 只属于 runtime backend

Targon 和 SSH 不再是训练框架中的 provider 语义，而是执行层 runtime backend。

允许：

- `TargonRuntime`
- `SshRuntime`
- `DockerRuntime`

禁止：

- 控制层直接 import Targon 启动细节
- 训练主干直接处理 Targon bundle transport
- 评测主干直接处理 SSH 远程启动

开发与调试例外：

- `remote_ops` sidecar 可以显式提供 Targon API / CLI 调试入口
- 这些入口只用于租机、查容量、查 workload、排查 SDK/runtime 缺口
- 它们不能成为正式 `train / eval / collect` 的主执行路径
- 它们不能让 renderer、pipeline、agent 重新依赖 Targon 平台细节

### 3. Bundle-first

执行层的稳定边界是 bundle，不是内存对象调用链。

每个 bundle 固定包含：

- `job.json`
- `inputs/`
- `scripts/entrypoint.sh`
- `artifacts/manifest.json`
- `runtime/`

任何 bundle 都必须：

- 可本地检查
- 可复制
- 可重放
- 可在无控制层时独立执行

### 4. Docker First

执行层开发默认走 Docker runtime。

开发流程：

1. 在现有基础镜像上手工探索
2. 把探索命令与问题记入执行层开发文档
3. 当流程稳定后，再固化为正式 Dockerfile

禁止一开始就同时维护：

- 宿主机第一路径
- Docker 第一路径
- 远程机第一路径

当前只允许 Docker 成为第一开发路径。

## 当前实施路线

### EX0 — 文档与目标切换

目标：

- 把 roadmap / progress / architecture / AGENTS 切换到控制层 / 执行层模型

完成定义：

- roadmap 已改写为两平面架构
- progress 已改写为 EX0-EX6
- 架构文档已加入控制层 / 执行层说明
- AGENTS 已加入 bundle-first / runtime-only / control-later 规则

### EX1 — 执行层 contracts + bundle

目标：

- 建立 `forge/execution/`
- 定义 bundle 与运行句柄
- 增加 `forge worker render` 与 `forge worker validate-bundle`

完成定义：

- 三类任务都能渲染为本地 bundle
- bundle 可校验、可人工检查、可重放

### EX2 — Docker runtime

目标：

- 建立 Docker 运行时主路径

完成定义：

- `forge worker run <bundle> --runtime docker`
- `forge worker status`
- `forge worker logs`
- `forge worker collect`
- `forge worker terminate`

### EX3 — Train / Eval / Collect renderer 接入真实业务

目标：

- 三类 renderer 都调用当前仓库里的真实业务入口

完成定义：

- train bundle 可生成真实 `swift_config.yaml`
- eval bundle 可生成真实 `eval_envs.py` 执行入口
- collect bundle 可生成真实数据采集入口

### EX4 — Targon / SSH runtime

目标：

- 同一个 bundle 可在 Docker、Targon、SSH 上运行

完成定义：

- `forge worker run ... --runtime targon`
- `forge worker run ... --runtime ssh`
- 至少一个训练 bundle 在 Targon 和 SSH 上通过真实测试

### EX5 — 旧执行路径清理

目标：

- 将当前 runtime-facing 主路径迁到 `forge worker`

完成定义：

- 旧执行路径已从 active surface 清除
- 新执行层是唯一运行路径
- 控制层只通过执行层运行任务

### EX6 — 镜像固化

目标：

- 将开发探索结果固化为正式 Dockerfile

完成定义：

- 一个开发调试镜像
- 一个部署执行镜像
- 两者共享同一 worker 运行入口

### CP0 — 控制层实验注册与控制面入口

目标：

- 建立 `forge/control/`
- 建立 `forge control`
- 迁移实验注册、状态管理与高层任务入口

完成定义：

- `ExperimentStore` 不再留在 pipeline 路径
- `forge control list/show/create/set-status`
- 根 CLI 公开 `control` 而不是旧 `exp`

### CP1 — 控制层训练提交与运行查询

目标：

- 让控制层负责高层训练提交与运行追踪

完成定义：

- `forge control render-train`
- `forge control submit-train`
- `forge control run-status`
- `forge control run-logs`
- `forge control collect-run`
- 控制层通过 execution runtime 查询状态与收集结果

### CP2 — 控制层评测与采集提交

目标：

- 让控制层不再只会提交训练，而是统一提交 `train / eval / collect`

完成定义：

- `forge control render-eval`
- `forge control submit-eval`
- `forge control render-collect-navworld`
- `forge control submit-collect-navworld`
- `run-status` / `run-logs` / `collect-run` / `terminate-run` 支持通过任务类型查询不同运行记录

### CP3 — Agent 经由控制层编排

目标：

- 让 agent 不再直接调 execution runtime 或 training pipeline
- 让 agent 通过 `ControlPlane` 发起和记录高层任务

完成定义：

- `TrainerAgent` 通过 `ControlPlane.submit_training(...)` 工作
- agent 评测结果回写实验记录
- `EvolutionLoop` 通过 control-plane-backed trainer 运行，而不是直接碰 execution plane

## 测试门槛

执行层里程碑必须同时满足：

### 代码测试

- bundle schema 与 renderer 单测
- worker CLI 单测
- runtime 关键参数映射测试

### 本地 smoke

- Docker runtime 至少跑通：
  - 一个 train bundle
  - 一个 eval bundle
  - 一个 collect bundle

### 真实运行验证

- 至少一个 train bundle 在 Targon runtime 成功运行
- 至少一个 train bundle 在 SSH runtime 成功运行
- 必须能查询状态、查看日志、收集 artifact

## 当前非目标

本阶段明确不做：

- agent 对执行层的全面接线
- 完整控制层决策环闭环
- 生产级调度协议或常驻 daemon

## Roadmap Change Policy

只有以下情况允许修改本文件：

- 控制层 / 执行层边界改变
- 执行层 milestone 顺序改变
- bundle 或 runtime 核心 contract 改变
- 测试 gate 规则改变
