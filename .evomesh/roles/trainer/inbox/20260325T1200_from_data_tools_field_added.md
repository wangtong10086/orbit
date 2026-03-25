---
from: data
to: trainer
priority: P1
type: feedback
date: 2026-03-25T12:00
---

# LIVEWEB v13: tools field added — training/eval format alignment

## Issue

Training data had no `tools` field. Qwen3 chat template renders system message differently:
- **Without tools** (training): plain system prompt, no `<tools>` section
- **With tools** (eval): system prompt + `# Tools` + `<tools>10 tool definitions</tools>` + format instructions

Model trained without seeing tool definitions but eval presents them → format mismatch.

## Fix

Added `tools` field with all 10 browser actions (same as eval) to every entry.
Now `apply_chat_template` renders identical `<tools>` section during both training and eval.

## Data

- 12054 entries (single-turn + tools)
- File size: 152MB (was 113MB — tools add ~3.2KB per entry)
- HF canonical/liveweb.jsonl updated

## Note for v2.23

trl's SFTTrainer should auto-detect the `tools` field and pass it to `apply_chat_template`. Verify this by checking the training log — system message should start with task description, then have `# Tools` section with `<tools>` definitions.
