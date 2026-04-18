# 02. Five-Stage Smoke

实验目录：`logs/real-tests/swe-five-stage-smoke-20260417/`  
原始记录：[README.txt](../../swe-five-stage-smoke-20260417/README.txt)

## 目标

- 验证五阶段收集链路是否能在真实任务上跑通
- MiniSWE / Codex 都要走真实 `sample -> relabel -> build-buckets -> train-verifier`

## 过程

- 使用真实 R2 task
- 本地 CPU + Docker runtime
- student: `Qwen/Qwen3-32B-TEE`
- teacher: `.env OPENAI_BASE_URL` + `gpt-5`

## 结果

- MiniSWE：
  - raw=1
  - failure point=1
  - critique=1
  - `B/C/V` 非空
- Codex：
  - raw=1
  - failure point=1
  - critique=1
  - `B/C/V` 非空
- `A=0`

## 记录到的问题

- Codex 初版请求协议有问题
- relabel/build manifest 的 append/rebuild 语义不合理

## 后续记录

- 后续实验记录加入 hidden oracle、issue rubric、shortlist 和 near-miss repair
