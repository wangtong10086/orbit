---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-28T14:00
---

# v2.28 OOM at step 2 — GPU 139/143GB peak

## 问题
训练 step 1 后静默崩溃。GPU 4 峰值 139GB（143GB 上限）。MemoryGym 条目 32k tokens 导致 batch 太大。

## 建议修复（任选一个）
1. **truncate MemoryGym 到 16384 tokens** — 减少峰值 VRAM
2. **加 `max_length 16384` 对 MemoryGym** — 或在数据层面截断
3. **去掉 MemoryGym** — 最简单，20000 条中 97% 被截断到 32k 也没什么训练价值
4. **降 grad_accum 到 2**（effective batch 16）— 峰值 VRAM 减半
