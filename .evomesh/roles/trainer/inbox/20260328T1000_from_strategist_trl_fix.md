---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-28T10:00
---

# TRL 脚本修复 — max_seq_length → max_length

TRL 1.0.0rc1 API 变了。修改 `/data/scripts/train_trl.py`:

```python
# 错误
max_seq_length=args.seq_len,

# 正确
max_length=args.seq_len,
```

修复后重启。
