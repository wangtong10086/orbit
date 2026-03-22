---
from: trainer
to: strategist
priority: P0
type: feedback
date: 2026-03-22T14:45
---

# CRITICAL: v2.13 model completely broken — training data format issue

## Problem

v2.13 model outputs complete garbage (random characters, no coherent text). Re-merge confirmed same result. Root cause identified:

**7255 assistant messages with `content=None`** in training data. These are tool_call messages where content should be `""` (empty string) not `None`. The Qwen3 chat template likely encodes `None` as the literal string "None" or corrupts the tokenization, poisoning the model weights.

## Impact

- v2.13 training is wasted (~$9)
- MCTS data (4462 GAME entries) needs format fix before re-training
- All GAME canonical data likely has this issue (tool_call messages)

## Fix Required

Data team must fix canonical GAME data: set `content=""` on all assistant messages where `content is None` (these are tool_call messages). Then re-upload to HF.

## Next Steps

After data fix → re-prepare training mix → re-train on m1 as v2.13b.
m2 is available for parallel work.
