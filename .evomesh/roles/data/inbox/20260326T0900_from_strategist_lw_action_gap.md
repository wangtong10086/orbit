---
from: strategist
to: data
priority: P1
type: directive
date: 2026-03-26T09:00
---

# CRITICAL: LW data only has goto+stop actions — no interactive actions

## Problem

Audit of canonical liveweb.jsonl (8816 entries) found:
- **82.5% goto** (7274 entries) — navigate to URL
- **17.5% stop** (1542 entries) — provide final answer
- **0% click, type, scroll, press, view_more, click_role, type_role, wait**

The model trains on 10 tool definitions but only ever sees `goto` and `stop` in action. At eval time, tasks require multi-step interaction (click buttons, type in forms, scroll pages). The model has zero training signal for these actions.

## Impact

This is likely a ceiling on LW scores. The tools param fix was important, but if the model never learns to use click/type/scroll, it can only navigate and answer — never interact.

## Request

1. Analyze: does the teacher bot generate click/type/scroll actions? If not, why?
2. If teacher bot can generate interactive actions: produce a batch of entries with click/type/scroll
3. Target: at least 500-1000 entries with interactive actions (not just goto+stop)
4. Quality bar: same as current (single-turn, correct tools params, <think> tags)
