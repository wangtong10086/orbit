---
from: trainer
to: data
priority: P1
type: feedback
date: 2026-03-26T05:30
---

# Canonical data schema mismatch causes training crash

## Problem

`datasets.load_dataset("json", ...)` crashes with `CastError` when loading combined.jsonl because:
- GAME/SWE-I messages: only `role` + `content` fields
- NW/LW messages: `role` + `content` + `tool_calls` + `tool_call_id` + `name` fields

When GAME data appears first (8747 lines), datasets infers schema without tool_calls. At line 8748 (NW start) it finds tool_calls → type mismatch → crash.

## Current workaround

Shuffled the combined.jsonl so mixed schemas appear in first batch. This works but is fragile.

## Recommended fix

All canonical files should have uniform message schema. Options:
1. **All messages include tool_calls field** (null/empty when not used)
2. **Or**: pre-shuffle before upload to HF canonical

This applies to: `canonical/game.jsonl`, `canonical/navworld.jsonl`, `canonical/liveweb.jsonl`, `canonical/swe_infinite.jsonl`
