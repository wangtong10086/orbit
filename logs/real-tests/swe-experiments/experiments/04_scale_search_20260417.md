# 04. Scale Search

实验目录：`logs/real-tests/swe-scale-search-20260417/`  
原始记录：[README.txt](../../swe-scale-search-20260417/README.txt)

## 目标

- 增大搜索预算
- 检查 revised 方法在真实任务上能否采到第一条 verified-correct trajectory

## 过程

- student: `Qwen/Qwen3-32B-TEE`
- 调大：
  - `localization_budget`
  - `localization_top_k`
  - `plan_samples_per_state`
  - `max_realizations`

## 结果

- 共 `12` 条真实 trajectories
- verified success：`0`
- `mini-rubocop` 多次改到正确文件邻域，但 patch 质量不够
- `codex` 基本还在 `no_patch`

## 额外发现

- `docker rm -f` cleanup 超时会把 sample 命令打崩
- 这轮顺手修了 runtime cleanup bug，并重跑了原始失败命令和下游 `relabel`

## 结论

- 单纯扩大搜索并不够
- 当时 student 模型质量已经成为明显瓶颈
