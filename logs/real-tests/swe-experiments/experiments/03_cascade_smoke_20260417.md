# 03. Cascade Smoke

实验目录：`logs/real-tests/swe-cascade-smoke-20260417/`  
原始记录：[README.txt](../../swe-cascade-smoke-20260417/README.txt)

## 目标

- 验证 hidden oracle + issue rubric + shortlist + near-miss repair 这条 revised path
- 同时跑真实 MiniSWE 和 Codex

## 过程

- student: `Qwen/Qwen3-32B-TEE`
- teacher: `gpt-5`
- 任务来自真实 R2
- 先 sample，再 relabel/build/train-verifier

## 结果

- MiniSWE：
  - 到达 near-miss
  - 产生 repair record
  - `B/C/V` 非空
- Codex：
  - 有 raw trajectory 和 failure point
  - `V` 非空
  - 没进入 near-miss gate

## 记录到的问题

- Mini student 响应过长，容易 timeout
- Codex 可能 plain-text 回复，不发 tool call

## 后续记录

- 后续实验继续扩大搜索预算并更换 student 模型
