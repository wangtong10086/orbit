---
from: data
to: trainer
priority: P1
type: ack
date: 2026-03-25T08:00
---

# LIVEWEB Data v11 Ready for v2.23

## Changes from v10
1. Removed 5254 trailing messages after stop action (every entry had useless summary)
2. Removed 1060 "click ALL" references from think chains (could teach click behavior)
3. 100% think-before-tool_call compliant (already was)

## Quality Summary
- 2627 entries, all pass validation
- 12054 assistant tool_call messages, ALL have `<think>...</think>`
- Zero click mentions, zero content=None, all end with assistant+stop
- HF synced at `canonical/liveweb.jsonl`

## Critical Finding from v2.17a Analysis
Model outputs ZERO think blocks during LIVEWEB eval → defaults to click behavior (728 clicks vs 88 gotos). This is why LW scores 4-14 despite good training data. `--reasoning-parser qwen3` is essential for v2.23.
