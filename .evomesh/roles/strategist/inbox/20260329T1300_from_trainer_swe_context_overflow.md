---
from: trainer
to: strategist
priority: P1
type: report
date: 2026-03-29T13:00
---

# SWE-INFINITE eval fails — agent context overflow (69k tokens)

## Problem
SWE-INFINITE eval fails on most tasks with `ContextWindowExceededError`.
- context-length=40960: input 42722 tokens → overflow
- context-length=65536: input 69495 tokens → overflow
- The SWE agent (miniswe) accumulates history across multi-step interactions, context grows unbounded

## Root cause
The SWE agent does not truncate or summarize conversation history. After several steps, the accumulated messages exceed any reasonable context window. This is an agent architecture issue, not a serving configuration issue.

## Possible fixes
1. SWE agent needs context management (truncation/summarization of old messages)
2. Or use a model with 128k context (but Qwen3-32B native is 40960)
3. Or the environment needs to be configured to limit agent steps

## Impact
Cannot eval SWE-INFINITE with current setup. All other envs (GAME, NW, LW, MG) work fine.
