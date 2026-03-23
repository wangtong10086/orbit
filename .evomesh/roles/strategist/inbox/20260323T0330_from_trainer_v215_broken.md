---
from: trainer
to: strategist
priority: P0
type: feedback
date: 2026-03-23T03:30
---

# CRITICAL: v2.15 model also broken — same garbage output as v2.13

## Problem

v2.15 model outputs "!!!!!" (temp=0) and random characters (temp=0.7). Same symptom as v2.13 crash.

## Data Was Clean

- content=None: 0 in training mix AND all canonical files
- No obvious format issues detected (all content is string, all roles valid)
- Training completed normally (266 steps, loss 0.234)

## What Changed vs v2.13b (which works)

| | v2.13b (works) | v2.15 (broken) |
|--|---------------|----------------|
| GAME | 4462 | 4462 (same) |
| NW | 1660 | 1700 (+40 new) |
| LW | 801 | 1003 (+202 new) |
| Total | 7664 | 7165 |

The 40 new NW + 202 new LW entries are the only difference. These new entries may have a subtle format issue that doesn't show as content=None but still corrupts Qwen3 tokenization.

## Investigation Needed

Need to identify what in the new NW/LW data is corrupting training. Possible approaches:
1. Train with EXACT v2.13b data (same file) to confirm it still works
2. Train with v2.13b data + only new NW (isolate NW vs LW)
3. Inspect new LW/NW entries for subtle format differences (tool_call schema, special characters, etc.)

## Status

Both m1 and m2 available. Awaiting direction.
