# Testing Guide

当前测试分三层：

1. 代码测试
2. smoke test
3. 真实运行测试

仅有单元测试通过，不足以证明 runtime 正常。

## 1. 代码测试

全量回归：

```bash
uv pip install -e .[all]
uv run --with pytest pytest -q
```

常用定向测试：

```bash
uv run --with pytest pytest -q tests/test_cli.py
uv run --with pytest pytest -q tests/test_control.py
uv run --with pytest pytest -q tests/test_execution.py
uv run --with pytest pytest -q tests/test_agent.py
uv run --with pytest pytest -q tests/test_env.py
```

## 2. Smoke Test

最小 smoke 关注“主路径能不能跑起来”，例如：

- `forge data aggregate`
- `forge worker render ...`
- `forge worker run ...`
- `forge control submit-train ...`
- `forge remote compute capacity`

建议每次改运行路径时至少覆盖：

- 一个 bundle 渲染
- 一个 runtime 启动
- 一个状态或日志查询

如果你是在另一台机器上做完整安装与 build 验证，直接按：

- [`test-runbook.md`](test-runbook.md)

执行。它包含：

- 安装矩阵
- `affinetes` 源码安装
- 本地 CLI / bundle smoke
- 根目录 Docker build
- 最小远程 smoke

## 3. 真实运行测试

运行时相关改动必须看：

- [`refactor/real-test-plan.md`](refactor/real-test-plan.md)

真实测试至少记录：

- 运行了哪些命令
- 用了哪些机器 / runtime / image
- run id / 日志路径 / 产物路径
- `pass / fail / blocked / not_run`

报告统一放在：

- `logs/real-tests/YYYY-MM-DD/`

## 4. 修复后的自测

如果修的是一个被真实测试发现的问题，还必须看：

- [`refactor/remediation-plan.md`](refactor/remediation-plan.md)

最少要重跑两类命令：

1. 原始失败命令
2. 至少一个依赖该修复的下游命令

少任意一项，都不算修复完成。

## 5. 什么时候用哪种测试

- 改本地纯逻辑：先跑代码测试
- 改 CLI 或 bundle 渲染：加 smoke test
- 改 runtime、远程执行、训练/评测/采集主路径：必须跑真实运行测试
- 改安装矩阵或命令可见性：必须跑 `-e .` / `.[control]` / `.[exec]` / `.[all]` 安装矩阵测试

## 6. 结果记录

如果这次工作属于重构推进的一部分，还要把结果同步到：

- [`refactor/progress.md`](refactor/progress.md)

项目文档负责说明“怎么测”，重构文档负责说明“这轮重构测到了哪一步”。
