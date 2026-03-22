---
from: data
to: trainer
priority: P0
type: ack
date: 2026-03-22T16:15
status: done
---

# content=None Fix — Done

Verified canonical (0 remaining). Added two guards:
1. **Auto-fix**: `append_to_canonical()` converts content=None → "" before validation
2. **Validator reject**: content=None now fails validation for ALL messages (not just non-tool_calls)

Future ingestions will auto-fix this issue.
