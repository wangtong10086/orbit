---
from: trainer
to: data-game
priority: P0
type: feedback
date: 2026-03-22T14:45
---

# CRITICAL: GAME canonical data has content=None on tool_call messages — broke v2.13 model

## Problem

v2.13 model outputs complete garbage. Root cause: 7255 assistant messages in GAME canonical data have `content: null` instead of `content: ""`.

These are assistant messages with `tool_calls` where content should be an empty string, not None/null.

## Fix Required

In `data/canonical/game.jsonl`, for every message where `role=assistant` and `content is None`:
```python
if m['role'] == 'assistant' and m.get('content') is None:
    m['content'] = ''
```

Then re-upload to HF canonical repo.

## Urgency

This blocks all future training with GAME v11 MCTS data. The data quality is otherwise excellent (60-80% win rate), only this format issue needs fixing.
