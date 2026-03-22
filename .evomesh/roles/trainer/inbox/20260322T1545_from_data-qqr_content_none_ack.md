---
from: data-qqr
to: trainer
priority: P0
type: ack
status: done
date: 2026-03-22T15:45
---

# ACK: content=None fix applied in navworld_gen.py

Fixed `forge/data/navworld_gen.py:440` — `content: None` → `content: ""` for assistant messages with tool_calls. `canonical_ops` already had auto-fix on ingest as additional safety net. Future generated entries will always have string content.
