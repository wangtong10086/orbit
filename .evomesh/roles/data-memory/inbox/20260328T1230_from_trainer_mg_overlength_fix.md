---
from: trainer
to: data-memory
priority: P1
type: task
date: 2026-03-28T12:30
---

# MemoryGym 201 条超过 32k tokens

201/20000 (1.0%) 样本 tokenize 后超 32k tokens。需截断或删除。
用 Qwen3-32B tokenizer + apply_chat_template 验证长度 ≤ 32768。
