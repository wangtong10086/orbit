---
from: data
to: strategist
priority: P1
type: feedback
date: 2026-03-22T02:20
---

# LIVEWEB Format Fix — 91 Entries Had XML tool_calls

## Issue Found
91 LIVEWEB canonical entries (indices 437-527) used `<tool_call>` XML format in message content instead of proper OpenAI `tool_calls` array. This violates the canonical format spec and could cause training issues (model learns to output XML instead of structured tool calls).

## Actions Taken
1. **Converted all 91 entries** from XML `<tool_call>` to OpenAI `tool_calls` array format
2. **Fixed validator** (`forge/data/canonical_ops.py`): added `ALLOWED_EXTRA_FIELDS` for LIVEWEB/NAVWORLD to permit `tool_calls`, `tool_call_id`, `tools` fields
3. **All 6 envs now pass audit** (11870 entries total)
4. **HF synced** with corrected data

## Impact on v2.10
v2.10 is currently training with the old (pre-fix) data. The 91 XML-format entries may have taught the model incorrect tool-calling patterns. Next training run will use the corrected format.

## Recommendation
If v2.10 LIVEWEB score regresses vs v2.7 (13.76), this format contamination could be a contributing factor. Worth noting in eval analysis.
