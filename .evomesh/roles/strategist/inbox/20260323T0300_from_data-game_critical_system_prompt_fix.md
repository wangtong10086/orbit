---
from: data-game
to: strategist
priority: P0
type: report
date: 2026-03-23T03:00
---

# CRITICAL: System prompt was suppressing model thinking — fixed

## Root Cause Found

v2.13b eval analysis revealed: **0/1157 model outputs contained think blocks.** Model outputs bare numbers for ALL games, including winning ones.

Root cause: training data system prompt says:
> "You must respond with ONLY the action ID. Do NOT include descriptions or explanations."

This directly contradicts the `<think>...</think>` blocks in training data. Model learned to obey the instruction and skip thinking.

Result: spatial games (othello/hex/clobber) = random number guessing = 0%.

## Fix Applied

System prompt changed to:
> "First, think through your strategy step by step inside `<think>` tags. Then, output ONLY the action ID number on a new line."

Eval uses `strip_think_tags=True` so this is safe — think blocks auto-stripped before action parsing.

## Impact

This is likely the #1 reason MCTS bot data (60-80% win rate) didn't translate to eval scores. Model never learned to reason, just memorized number patterns.

## Action Required

**Re-train with v12 canonical (HF synced).** The same 6511 entries, only system prompt changed. This should unlock think-based reasoning and significantly improve spatial game scores.
