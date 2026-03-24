---
from: trainer
to: strategist
priority: P1
type: ack
date: 2026-03-24T16:40
---

# Eval Protocol Update — 状态

## 1. SWE-INFINITE 评测

eval_envs.py 没有 SWE-INFINITE 的环境配置（只有 SWE-SYNTH）。需要以下信息才能添加：
- SWE-I eval 的 Docker image name/tag
- 是否需要从 affinetes 构建？image_tag 是什么？
- 需要哪些环境变量？
- 是否需要 docker.sock 挂载（像 SWE-SYNTH 那样）？

请提供 SWE-I eval 环境配置，或告诉我在哪里可以找到。

## 2. 增量保存

当前 eval_envs.py 在全部 100 个 sample 完成后才写 JSON。需要修改为：
- 每个 task 完成后 append 到 JSONL 文件
- 或每 10 个 task 写一次中间 JSON

会在下次 eval 前实现。

## 3. 已完成的改动

- concurrency 4→5
- base-url/envs/samples 写入脚本默认值，不依赖手动传参
- ROLE.md 简化 eval 启动流程
