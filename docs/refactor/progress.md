# 重构进度

更新时间：2026-04-04

## 当前活跃里程碑

- `M4. 真实验证闭环`
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

## 当前结论

本轮首先恢复了权威文档，再继续后续架构收敛。

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
5. 当前公开执行矩阵为 `local + host_process`、`local + docker_image`、`targon_rental + docker_image`
6. 当前 Targon 路径只实现 rental 语义
7. execution 核心已不再承载 train / eval / collect task-specific renderer 与 spec

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

- `python -m forge --help`
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

## 当前已执行验证

### CLI 帮助面

已运行：

- `python -m forge --help`
- `python -m forge control --help`
- `python -m forge worker --help`
- `python -m forge data --help`
- `python -m forge remote --help`
- `python -m forge monitor --help`

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

结果摘要：

- 全量 `tests/` 通过
- 真实验证后新增的 targeted compute / execution 回归测试通过

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

- `forge.execution.runtimes.TargonRentalDockerRuntime.logs()` 在 foreground `--rm` 场景下会优先返回 `docker logs` 的 “No such container”，而不是回退到 bundle artifacts
- `forge.compute.ssh.SshBackend.download()` 在 Targon bannered host 上会在 `scp -r` 阶段卡住，导致 `control run collect` 长时间不返回

补充说明：

- `GAME/othello` 的 collect 任务在 Targon 默认 image 上会因缺少 `pyspiel` 失败；这被记录为任务镜像依赖问题，不阻塞 control/execution/Targon 闭环的完成
- 为了完成 control -> Targon 真闭环，本轮使用 `NAVWORLD` collect 作为远端真实任务

## M0 完成判定

`M0. 文档真相源恢复` 现已满足路线图中的完成标准：

1. `README.md` 与 `docs/` 已互相一致
2. `AGENTS.md` 指向的 refactor 文档已存在
3. 当前 CLI、测试现实、架构边界均已有明确文档

## 当前结论

`M4. 真实验证闭环` 已完成：

1. 已使用新的隔离 Targon rental 机器完成 worker 级 smoke
2. 已使用 control plane 完成 submit -> status -> logs -> collect 闭环
3. 已将真实验证中暴露的 runtime / transfer 缺陷修复并以 targeted tests 固化
