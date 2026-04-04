# 重构路线图

本文档描述当前重构的长期目标与里程碑。

## 长期目标

Affine Swarm 的目标架构是一个清晰的两平面系统：

- `control plane`
- `execution plane`

其中：

- control plane 只负责编排、提交、追踪、元数据记录
- execution plane 只负责执行
- 训练 / 评测 / 采集作为任务层或 pipeline 层能力，与 execution plane 解耦

## 目标架构原则

### 1. Control Plane 只面向执行模板

control plane 最终不直接依赖具体 runtime target。

control plane 应只依赖：

- 任务请求
- 已注册的 `exec template`
- 提交结果与状态查询接口

### 2. 执行模板是注册单位

执行模板不是机器实例，而是执行策略描述。

模板至少应描述：

- `id`
- `placement`
- `launch_mode`
- `default_image`
- `resources`
- `env policy`
- `artifact policy`
- `allowed_overrides`

### 3. 执行维度拆成两个正交轴

已确认的目标维度：

- placement
  - `local`
  - `targon_rental`
- launch mode
  - `host_process`
  - `docker_image`

### 4. Execution Plane 与任务语义解耦

execution plane 只处理通用 bundle 与执行契约。

train / eval / collect：

- 不属于 execution plane 的核心抽象
- 应在更高层先被渲染为通用 bundle

### 5. Targon 只支持 rental

当前路线图不为以下路径设计统一抽象：

- serverless
- app

这两类能力不在当前 execution abstraction 范围内。

## 当前偏差

当前代码与目标相比仍存在：

1. experiment 持久化仍采用 YAML 文件模型，而不是更强事务语义的状态存储
2. 个别 domain/data CLI 仍直接拼 task builder + worker 调用，而不是统一走 control plane

## 里程碑

### M0. 文档真相源恢复

目标：

- 建立 `docs/` 与 `docs/refactor/`
- 用当前代码和当前用户指令重写权威文档
- 明确哪些旧文档是历史材料

完成标准：

- `README.md` 与 `docs/` 互相一致
- `AGENTS.md` 指向的 refactor 文档存在
- 当前 CLI、测试现实、架构边界都有明确文档

### M1. Execution 抽象归一

目标：

- 从 execution plane 中移除 train / eval / collect 的核心语义抽象
- 让 execution plane 面向通用 bundle 和执行请求

完成标准：

- task-specific renderer 不再驻留于 execution plane 核心
- execution contracts 不再成为任务语义总集散地
- public worker CLI 不再暴露 task-specific render 命令

### M2. Control Plane 改为模板驱动

目标：

- control submit 改为面向 `exec template`
- control plane 不再直接构造具体 runtime target

完成标准：

- control contract 与 CLI 不再直接依赖具体 target union
- run record 保存模板快照与解析结果

### M3. Local / Targon 执行矩阵收敛

目标：

- 明确支持：
  - `local + host_process`
  - `local + docker_image`
  - `targon_rental + docker_image`
  - `targon_rental + host_process`

完成标准：

- placement 与 launch mode 语义分离
- 对支持矩阵都有明确代码与文档

Targon GPU 执行附加约束：

- 不默认依赖 rental 内部的 Docker-in-Docker GPU 路径
- 对需要 GPU 的 Targon 任务，优先使用 direct-image rental + `host_process`

### M4. 真实验证闭环

目标：

- 对新的 control/execution 边界做真实运行验证

完成标准：

- 本地执行 smoke
- Targon rental 执行 smoke
- control -> execution 闭环验证
- 文档、测试、真实运行记录一致

### M5. Core Shell 与 Plugin Contracts

目标：

- 引入 `forge/core/*` 作为通用内核壳层
- 引入显式 `TaskPlugin` / `TaskRegistry`
- 禁止 `core` 反向依赖具体任务实现

完成标准：

- `forge/core/*` 存在并承载 generic contracts / control / execution / templates / experiments
- `forge/tasks/*` 通过显式 registry 接入
- `forge/core` 静态检查不再 import `forge.tasks`

### M6. Task Specs 与 Bundle Builders 迁出 Control

目标：

- 将 task-specific spec / bundle builder 迁到 `forge/tasks/*`
- 让 `forge/control/task_specs.py` 与 `forge/control/bundles.py` 退化为兼容层

完成标准：

- 生产代码主路径从 `forge/tasks/*` 导入 task spec / builder
- `forge/control/task_specs.py` 与 `forge/control/bundles.py` 不再承载主实现

### M7. Generic Control Kernel 落地

目标：

- 用 `CoreControlService` 承载 generic `prepare_task / submit_task`
- 让 `ControlPlane` 成为 task-aware facade，而不是主实现

完成标准：

- run record 持久化 `task_type`、`task_request`、`task_summary`
- `submit_training / submit_eval / submit_collect` 只做 facade 适配

### M8. CLI 改为 Plugin-Backed

目标：

- 保持 `forge control` 用户命令名不变
- 让 CLI 实现经 task plugin + core kernel 走主路径

完成标准：

- CLI 主路径不再依赖旧的 mixed-responsibility builder/spec 实现
- `forge data` 中活跃路径不再 import `forge.control.bundles` / `forge.control.task_specs`

### M9. Boundary Hardening 与真实验证回归

目标：

- 用静态测试锁定 `core -> task plugins` 单向边界
- 补足真实执行回归，验证新的 core/tasks split

完成标准：

- 新增 core boundary tests
- 真实验证覆盖 local worker、local control、Targon worker、Targon control
- 修复并回归验证在本轮真实测试中暴露的问题
