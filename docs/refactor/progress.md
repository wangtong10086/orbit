# 重构进度

更新时间：2026-04-04

## 当前活跃里程碑

- `M9. Boundary Hardening 与真实验证回归`
- 状态：`completed`

## 最近完成的里程碑

- `M0. 文档真相源恢复`
- 状态：`completed`
- `M1. Execution 抽象归一`
- 状态：`completed`
- `M2. Control Plane 改为模板驱动`
- 状态：`completed`
- `M3. Local / Targon 执行矩阵收敛`
- 状态：`completed`
- `M4. 真实验证闭环`
- 状态：`completed`
- `M5. Core Shell 与 Plugin Contracts`
- 状态：`completed`
- `M6. Task Specs 与 Bundle Builders 迁出 Control`
- 状态：`completed`
- `M7. Generic Control Kernel 落地`
- 状态：`completed`
- `M8. CLI 改为 Plugin-Backed`
- 状态：`completed`

## 当前结论

本轮首先恢复了权威文档，再继续完成 `core / task plugins / sidecars`
边界收敛。

原因：

- `AGENTS.md` 与 `README.md` 都指向 `docs/refactor/*`
- 但仓库当时不存在 `docs/` 目录
- 旧文档之间存在明显冲突
- 旧文档与当前代码实现也存在明显漂移

## 已确认的架构事实

1. 当前仓库已经形成 control plane / execution plane / sidecar 的基本结构
2. 当前 `control` 负责 experiment、template、prepare、submit、run 查询与回收
3. 当前 `worker` 负责通用 bundle 的 run、status、logs、collect、terminate
4. 当前 execution template 注册表已落地为仓库 YAML
5. 当前公开执行矩阵为 `local + host_process`、`local + docker_image`、`targon_rental + docker_image`、`targon_rental + host_process`
6. 当前 Targon 路径只实现 rental 语义
7. execution 核心已不再承载 train / eval / collect task-specific renderer 与 spec
8. 通用内核已集中到 `orbit/core/*`
9. 内建任务插件已集中到 `orbit/tasks/{training,evaluation,collection}`
10. `ControlPlane` 现为 facade，generic orchestration 主实现为 `CoreControlService`

## 已确认的文档漂移

### 漂移 1：权威文档路径缺失

现象：

- `README.md` 引用 `docs/README.md` 与 `docs/refactor/*`
- `AGENTS.md` 要求先读 `docs/refactor/*`
- 但仓库当时没有 `docs/`

处理：

- 已恢复 `docs/` 与 `docs/refactor/`
- 已让 `README.md`、`AGENTS.md`、`docs/`、`docs/refactor/` 互相对齐
- 已将 `PLAYBOOK.md` 与 `CLAUDE.md` 明确标记为历史文档入口

### 漂移 2：CLI 安装矩阵叙事与当前包行为不一致

现象：

- 旧叙事认为不同 extra 会严格控制根命令可见性
- 当前根 CLI 仍会显示全部命令族

证据：

- `python -m orbit --help`
- `tests/test_cli.py` 中相关 install-matrix 测试失败

处理：

- 文档改为按当前实际行为描述
- 相关 CLI 测试已同步改为匹配当前实现

### 漂移 3：训练测试不是纯仓库自包含

现象：

- `tests/test_training.py` 在 collection 阶段依赖 `affinetes`

证据：

- `pytest -q tests/test_training.py -q`

处理：

- 文档明确标记外部依赖前提

## M5-M9 代码收敛

本轮新增并完成：

1. 建立 `orbit/core/*`
2. 建立 `orbit/tasks/*` plugin 层
3. 将 task-specific specs / builders 迁出 control 主实现
4. 将 `ControlPlane` 收敛为 plugin-backed facade
5. 为 `orbit/core` 增加静态边界测试

本轮真实测试中发现并修复：

- `orbit.cli_worker.worker_run()` 未持久化 `RunHandle`，导致真实 `worker collect`
  无法跟进同一 bundle 的前序 run
- `orbit.execution.runtimes.create_bundle_archive()` 会把本地旧 `runtime/`
  与旧 artifacts 一起打进 remote bundle，导致远端 collect 后可能恢复出
  stale run metadata
- 新 provision 的 Targon systemd rental 缺少 NVIDIA container toolkit，
  会在真实 `docker run --gpus all` 路径上失败；本轮按验证 runbook 现场补齐
  并回归原命令

## 当前已执行验证

### CLI 帮助面

已运行：

- `python -m orbit --help`
- `python -m orbit control --help`
- `python -m orbit worker --help`
- `python -m orbit data --help`
- `python -m orbit remote --help`
- `python -m orbit monitor --help`

结果：

- 全部可运行

### pytest

已运行：

- `pytest -q tests/test_control.py tests/test_execution.py tests/test_cli.py -q`
- `pytest -q tests/test_agent.py -q`
- `pytest -q tests/test_data_ops.py tests/test_training.py -q`
- `pytest -q tests/test_data_cli.py tests/test_pipeline.py tests/test_remote_game_longrun.py -q`
- `pytest -q tests -q`
- `pytest -q tests/test_compute.py tests/test_execution.py -q`
- `pytest -q tests/test_execution.py tests/test_control.py tests/test_core_boundaries.py tests/test_cli.py -q`

结果摘要：

- 全量 `tests/` 通过
- 真实验证后新增的 targeted compute / execution 回归测试通过
- 新增 core boundary / bundle archive / worker handle regression tests 通过

### 真实执行

已运行：

- local host-process worker smoke，结果成功
- local docker worker smoke，结果成功
- control prepare train + worker validate-bundle，结果成功
- control submit collect (`GAME/othello`, `template=local-host`) -> run status -> run collect，结果成功
- Targon rental worker smoke，结果成功
- control submit collect (`NAVWORLD`, `template=targon-rental-docker`) -> run status -> run logs -> run collect，结果成功

Targon 验证机：

- workload: `wrk-pvsfcppud27o`
- name: `affine-refactor-validation-20260404-systemd-keyed`
- machine alias: `affine-refactor-validation-h200x1`
- host: `72.46.85.157:30559`
- image: `ghcr.io/manifold-inc/ubuntu-systemd-docker:v1`
- resource: `h200-small`

本轮真实验证中发现并修复：

- `orbit.execution.runtimes.TargonRentalDockerRuntime.logs()` 在 foreground `--rm` 场景下会优先返回 `docker logs` 的 “No such container”，而不是回退到 bundle artifacts
- `orbit.compute.ssh.SshBackend.download()` 在 Targon bannered host 上会在 `scp -r` 阶段卡住，导致 `control run collect` 长时间不返回

补充说明：

- `GAME/othello` 的 collect 任务在 Targon 默认 image 上会因缺少 `pyspiel` 失败；这被记录为任务镜像依赖问题，不阻塞 control/execution/Targon 闭环的完成
- 为了完成 control -> Targon 真闭环，本轮使用 `NAVWORLD` collect 作为远端真实任务

### M5-M9 真实执行

已运行：

- local host worker smoke on `/tmp/affine-m5m9-worker-host`
- local docker worker smoke on `/tmp/affine-m5m9-worker-docker`
- control submit collect (`GAME/othello`, `template=local-host`) on `/tmp/affine-m5m9-debug`
- isolated Targon rental worker smoke on workload `wrk-65rlqubugtj0`
- isolated Targon control submit smoke on `/tmp/affine-m5m9-control-targon-nav`

Targon 验证机：

- workload: `wrk-65rlqubugtj0`
- name: `affine-m5-m9-validation-20260404-systemd-keyed`
- machine alias: `affine-m5-m9-validation-h200x1`
- host: `72.46.85.157:31673`
- image: `ghcr.io/manifold-inc/ubuntu-systemd-docker:v1`
- resource: `h200-small`

关键证据：

- `logs/real-tests/2026-04-04/m5-m9-validation/local-worker-host/*`
- `logs/real-tests/2026-04-04/m5-m9-validation/local-worker-docker/*`
- `logs/real-tests/2026-04-04/m5-m9-validation/targon/workload.json`
- `logs/real-tests/2026-04-04/m5-m9-validation/targon/nvidia-toolkit-install.log`
- `logs/real-tests/2026-04-04/m5-m9-validation/targon/control-status.json`
- `logs/real-tests/2026-04-04/m5-m9-validation/targon/control-logs.txt`
- `logs/real-tests/2026-04-04/m5-m9-validation/targon/control-collect.json`

环境收尾：

- 验证 workload `wrk-65rlqubugtj0` 已在完成后删除
- `machines.json` 已恢复为非验证状态，不保留一次性 validation alias

## M0 完成判定

`M0. 文档真相源恢复` 现已满足路线图中的完成标准：

1. `README.md` 与 `docs/` 已互相一致
2. `AGENTS.md` 指向的 refactor 文档已存在
3. 当前 CLI、测试现实、架构边界均已有明确文档

## 当前结论

`M5-M9` 已完成：

1. `orbit/core/*` 已成为 generic control/execution/contracts 主路径
2. `orbit/tasks/*` 已成为 training/evaluation/collection 的内建 plugin 层
3. `orbit/control/*` 与 `orbit/execution/*` 的旧 surface 已退化为兼容层
4. 主测试已迁到新主路径，并新增 core boundary / archive hygiene 回归测试
5. 已在新的隔离 Targon rental 机器上完成 worker 与 control 的真实回归

## 后续审计修正：主路径 compatibility 收尾

日期：`2026-04-04`

后续审计发现：

1. `orbit/cli_control.py` 与 `orbit/cli_worker.py` 仍通过 `orbit.control` /
   `orbit.execution` package-level compatibility surface 进行主 wiring
2. 部分主测试仍以 compatibility surface 为默认导入面
3. `orbit data liveweb-gen -m` 仍硬编码 `targon_rental + docker_image`
4. `README.md` 的远端 submit 示例仍默认展示 `targon-rental-docker`

本轮修正：

- `orbit/cli_control.py` 改为直接装配 `orbit/core/*`
- `orbit/cli_worker.py` 改为直接导入 `orbit/core/*`
- `orbit/tasks/training/launcher.py` 改为面向 generic `CoreControlService`
- `tests/test_control.py`、`tests/test_training_launch.py`、`tests/test_training.py`、
  `tests/test_execution.py`、`tests/test_data_ops.py` 等迁离 package-level
  compatibility imports
- `orbit data liveweb-gen -m` 改为 `targon_rental + host_process`
- `README.md` 的 Targon submit 示例改为 `targon-rental-host`
- `docs/cli.md` 增补了 Targon host-first 与 data 直达便捷路径的说明

静态审计：

- `rg -n "from orbit\\.control import|from orbit\\.execution import|from orbit\\.control\\.task_specs|from orbit\\.control\\.bundles" tests orbit/cli_*.py README.md docs`
  结果为空

本轮测试：

- `pytest -q tests/test_control.py tests/test_training_launch.py tests/test_cli.py tests/test_data_cli.py tests/test_agent.py tests/test_execution.py -q`
- `pytest -q tests -q`
- `python -m orbit control --help`
- `python -m orbit worker --help`
- `python -m orbit data --help`

## 后续审计修正：Agent Layer 脱离 facade API

日期：`2026-04-04`

问题：

- `orbit/agent/*` 仍依赖 `orbit.control.service.ControlPlane` 的 task-aware
  facade 方法，例如 `submit_training()`
- `tests/test_agent.py` 也仍以该 facade 作为主装配入口

修正：

- `orbit/agent/trainer.py` 改为依赖 generic `CoreControlService`
- agent 训练提交改为 `TaskSubmission(task_type="training") -> submit_task()`
- 训练 spec 校验改由 `TrainingPipeline` 负责，而不是经 `ControlPlane.training`
- `orbit/agent/loop.py`、`orbit/agent/strategist.py`、`orbit/agent/data_agent.py`
  的核心导入切换到 `orbit/core/*`
- `tests/test_agent.py` 改为通过 `CoreControlService` + task registry 装配

静态审计：

- `rg -n "orbit\\.control|orbit\\.execution" orbit/agent | sort`
  结果为空

测试：

- `pytest -q tests/test_agent.py tests/test_control.py tests/test_training_launch.py -q`
- `pytest -q tests -q`

## 后续审计修正：compatibility package surface 收紧

日期：`2026-04-04`

问题：

- `orbit/control/__init__.py` 与 `orbit/execution/__init__.py` 仍保留
  package-level re-export surface
- `orbit data liveweb-gen -m` 虽已改为 host-first，但仍直接调用 worker，
  还没有经 control kernel
- `AGENTS.md` 中 execution-plane ownership 仍写成 `orbit/execution/`

修正：

- `orbit/control/__init__.py` 改为仅保留兼容性说明，不再导出 package-level
  symbols
- `orbit/execution/__init__.py` 改为仅保留兼容性说明，不再导出 package-level
  symbols
- `orbit data liveweb-gen -m` 改为经 `CoreControlService.submit_task()` 提交
  collection task，而不是 shell 出 `orbit worker ...`
- `AGENTS.md` 改为声明 `orbit/core/execution/` 是主 execution surface，
  `orbit/execution/` 仅为兼容层

静态审计：

- `rg -n "from orbit\\.control import|import orbit\\.control($|\\.)|from orbit\\.execution import|import orbit\\.execution($|\\.)" orbit tests | sort`
  结果为空

测试：

- `pytest -q tests/test_data_cli.py tests/test_control.py tests/test_training_launch.py tests/test_agent.py -q`
- `pytest -q tests -q`

## 后续审计修正：Targon Direct-Image Host Path

日期：`2026-04-04`

问题：

- 先前 Targon 真实路径默认把 rental 当作 Docker 宿主
- 这会让执行依赖 Docker-in-Docker GPU 语义
- 用户确认这不符合预期；预期路径应为“rental 直接以目标镜像启动，再作为 execution host 执行 bundle”

修正：

- 新增 public template：`targon-rental-host`
- 新增 backend：`targon_rental_host_process`
- 执行方式改为：
  - direct-image rental
  - SSH into rental
  - stage project/bundle archives
  - execute bundle directly on rental host process

真实验证：

- new isolated rental:
  - workload: `wrk-trnf5w09ih95`
  - alias: `affine-targon-host-dropbear-h200`
  - image: `wangtong123/orbit:latest`
  - ssh port: `72.46.85.157:32753`
- worker host-process smoke:
  - bundle: `/tmp/affine-targon-host-worker`
  - result: success
- control submit collect smoke:
  - experiment dir: `/tmp/affine-targon-host-control`
  - template: `targon-rental-host`
  - task: `collect(NAVWORLD, n=1)`
  - result: success

证据：

- `logs/real-tests/2026-04-04/targon-host-validation/rental-dropbear-create-response.json`
- `logs/real-tests/2026-04-04/targon-host-validation/rental-dropbear-deploy-response.json`
- `logs/real-tests/2026-04-04/targon-host-validation/rental-dropbear-state-latest.json`
- `logs/real-tests/2026-04-04/targon-host-validation/worker-status.json`
- `logs/real-tests/2026-04-04/targon-host-validation/worker-logs.txt`
- `logs/real-tests/2026-04-04/targon-host-validation/worker-collect.json`
- `logs/real-tests/2026-04-04/targon-host-validation/control-status.json`
- `logs/real-tests/2026-04-04/targon-host-validation/control-logs.txt`
- `logs/real-tests/2026-04-04/targon-host-validation/control-collect.json`
