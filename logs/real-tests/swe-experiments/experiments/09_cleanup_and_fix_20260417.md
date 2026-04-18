# 09. Cleanup And Fix

实验目录：`logs/real-tests/swe-cleanup-and-fix-20260417/`  
原始记录：[README.txt](../../swe-cleanup-and-fix-20260417/README.txt)

## 目标

- 修复本地环境污染
- 加 probe gating / rubric fallback
- 用同一 recipe 重新验证 representative tasks

## 过程

- Docker 大清理：
  - 移除非白名单临时容器
  - prune 无用镜像
- 新增：
  - student probe
  - teacher probe
  - docker probe
  - rubric degraded path

## 结果

- 磁盘从 `2.7G` 可用恢复到 `117G`
- 代表任务 rerun 开始产生更诚实的 changed-files / verify-fail
- 但仍然没有 success

## 后续记录

- 后续实验记录继续围绕 realization action-space 调整
