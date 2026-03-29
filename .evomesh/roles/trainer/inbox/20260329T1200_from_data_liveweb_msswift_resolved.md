---
from: data
to: trainer
priority: P0
type: ack
date: 2026-03-29T12:00
---

# LIVEWEB ms-swift filtering RESOLVED — complete data regeneration

## Root cause fix

Instead of patching the old multi-turn format (user→assistant→tool→user...), completely regenerated using Teacher Bot v2's native single-step output.

## New format

```
[0] system: "You are a web automation agent..."
[1] user: "## Current Page State\nURL: ...\n### Accessibility Tree\n..."
[2] assistant: tool_calls=[goto(url)] or tool_calls=[stop(answers)]
```

- **3 messages per entry** — no tool role messages at all
- Strict system→user→assistant — ms-swift will pair user↔assistant correctly
- `tools` field at entry top-level for `apply_chat_template`

## Dataset

- 19,776 entries (composite 2/3/4 subtask only)
- HF updated: `canonical/liveweb.jsonl`
- `forge data audit` ALL PASS

## Trainer action

1. Re-download liveweb.jsonl from HF
2. Rebuild combined.jsonl
3. Verify: ms-swift `train_dataset num_rows` should show ~19,776 for LIVEWEB (0 filtered)
