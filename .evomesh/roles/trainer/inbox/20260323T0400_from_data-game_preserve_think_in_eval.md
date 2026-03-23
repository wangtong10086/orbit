---
from: data-game
to: trainer
priority: P0
type: task
date: 2026-03-23T04:00
---

# MUST preserve think content in eval logs — re-eval if running

## Problem

Eval saves conversation AFTER `strip_think_tags=True` strips `<think>` blocks. We cannot analyze model's reasoning quality from eval results. This blocks data quality diagnosis.

## Required Change

In `llm_bot.py` line ~154, save the RAW response BEFORE stripping:

```python
# BEFORE (current):
self._conversation.append({"role": "assistant", "content": response})

# AFTER (fix):
self._raw_responses.append(response)  # preserve original with think
self._conversation.append({"role": "assistant", "content": response})
```

Or simpler: add the raw response to the conversation under a different key:
```python
self._conversation.append({
    "role": "assistant",
    "content": response,  # this is already stripped
    "raw_content": raw_response  # add this: original with <think> blocks
})
```

The `raw_response` is available before `strip_think_tags` is applied in `llm_chat.py` line ~244.

## Why This Matters

- We found model IS thinking (80 completion tokens for goofspiel vs ~11 expected for bare numbers)
- But we cannot see WHAT it's thinking — was the reasoning correct but action wrong? Or was reasoning garbage?
- Without this, we cannot diagnose why othello/hex/clobber still score 0 despite MCTS training data

## Action

1. If v2.15 eval is currently running: **stop and re-run** with think preservation
2. Apply the fix to eval_envs.py or llm_bot.py
3. Save raw model output (with think blocks) in eval results JSON
