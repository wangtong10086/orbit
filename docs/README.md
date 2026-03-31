# Documentation

`docs/` 只放当前有效的长期文档，按“先看什么、再看什么”组织。

## 快速导航

先看全局：

- [architecture-zh.md](architecture-zh.md)
  系统架构、模块边界、设计原则。
- [cli.md](cli.md)
  公开 CLI 与常用命令。
- [operations.md](operations.md)
  日常运行、远程机器、镜像、日志和产物处理。
- [testing.md](testing.md)
  测试类型和执行方式。

看 `GAME`：

- [game-generators.md](game-generators.md)
  `GAME` generator registry、teacher family、policy model 路线与模块边界。
- [game-selfplay-local-run.md](game-selfplay-local-run.md)
  本地 7 卡 self-play 长跑、状态字段、恢复语义。

看完整验证步骤：

- [test-runbook.md](test-runbook.md)
  从安装到最小远程 smoke 的执行清单。

看重构治理：

- [refactor/README.md](refactor/README.md)
- [refactor/roadmap.md](refactor/roadmap.md)
- [refactor/progress.md](refactor/progress.md)
- [refactor/real-test-plan.md](refactor/real-test-plan.md)
- [refactor/remediation-plan.md](refactor/remediation-plan.md)

## 约定

- `docs/` 根目录描述“当前系统怎么工作、怎么用”。
- `docs/refactor/` 只保留路线、进度、验证计划这类治理文档。
- 已废弃的阶段性说明不再作为当前文档集的一部分。
