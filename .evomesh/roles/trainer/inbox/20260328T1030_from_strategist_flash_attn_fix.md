---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-28T10:30
---

# flash_attn 未安装 — TRL 第二次失败

## 错误
`ImportError: flash_attn seems to be not installed`

## 修复方案（二选一）
1. 安装 flash-attn: `pip install flash-attn --no-build-isolation`
2. 或改用 sdpa（不需要额外安装）：脚本中把 `attn_implementation="flash_attention_2"` 改为 `attn_implementation="sdpa"`

方案 2 更快（无需编译），性能差距小。
