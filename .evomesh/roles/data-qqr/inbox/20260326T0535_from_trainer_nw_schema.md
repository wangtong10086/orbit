---
from: trainer
to: data-qqr
priority: P1
type: feedback
date: 2026-03-26T05:35
---

# NW canonical data has tool_calls in messages — causes training schema mismatch

NW messages contain `tool_calls`, `tool_call_id`, `name` fields. GAME messages only have `role`+`content`. When combined for training, `datasets.load_dataset` crashes because schema differs between environments.

Workaround: shuffle data so mixed schemas appear early. But ideally NW canonical should be consistent with other envs — either all envs include these fields or none do.
