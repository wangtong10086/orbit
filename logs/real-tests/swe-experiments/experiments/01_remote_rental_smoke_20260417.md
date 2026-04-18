# 01. Remote Rental Smoke

实验目录：`logs/real-tests/swe-collect-smoke-20260417/`  
原始记录：[README.txt](../../swe-collect-smoke-20260417/README.txt)

## 目标

- 用两台新的 Targon rental 跑 MiniSWE / Codex 小规模真实收集
- 任务必须从真实 R2 拉取
- 产物需要能 `swe-sync`

## 过程

- 先尝试基于 raw Targon API 创建 fresh rental
- 分别尝试：
  - `sshd`-first 初始化
  - dropbear-only 初始化
- 同时尝试定位可用 teacher endpoint

## 结果

- 两个格式都没有真正启动 `swe-collect`
- 没有远端 collector output
- 没有 `canonical/swe_infinite.jsonl`
- 没有 `swe-sync`

## 记录到的阻塞

- rental SSH bootstrap 不可用：
  - `sshd` 路径卡在 `provisioning`
  - dropbear 路径到 `running` 后仍然 `connection refused`
- 原计划 teacher endpoint 不稳定，后来直接 `404`

## 后续记录

- 后续实验记录为本地 CPU + Docker + 真实 R2 task
