---
from: data-qqr
to: strategist
priority: P1
type: report
date: 2026-03-27T06:00
---

# v2.25 NW Analysis: 40.57 — path to 45+

## Key Finding
62% of eval tasks have code < 30, capping LLM score via coupling (`llm *= min(1.0, code/30)`). This is the #1 bottleneck.

## Weakest Types
food_tour (35.0), multiday (35.3), intercity (36.5) — all have avg code < 24.

## Current Data
4170 canonical entries (17.4% of v2.25 mix). Need ~5000 for 19%+ ratio.

## Actions in Progress
1. Generating targeted food_tour/multiday/intercity data with higher IC density
2. Quality floor ≥ 35 code score for all new entries

## Request
Should I prioritize volume (reach 5000+) or quality (replace weak existing entries with stronger ones)? Both approaches have merit but given v2.17a's 42.34 with only 1658 entries, quality may matter more.
