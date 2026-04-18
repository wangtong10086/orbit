# 13. Checkpoint Tree

实验目录：`logs/real-tests/swe-checkpoint-tree-20260417/`  
原始记录：[README.txt](../../swe-checkpoint-tree-20260417/README.txt)

## 目标

- 把 realization queue 替换成 checkpointed tree search
- 用 teacher state summary 做 prior/value

## 过程

- 新增：
  - `search/checkpoints.jsonl`
  - `search/nodes.jsonl`
  - `search/teacher_state_summaries.jsonl`
- 在真实 fixed-task 上开始 partial rerun

## 中途修复

- OpenAI-compatible timeout 过长
- root teacher summary eager 串行
- nested `patch` action 被误判为 `no_action`

## 结果

- 新主路径已经在真实任务上跑活
- 但这轮只完成 partial validation
- 没有完成三组 fixed-task 的完整 `sample -> relabel -> build-buckets`

## 后续记录

- 后续实验记录为 hypothesis-tree
