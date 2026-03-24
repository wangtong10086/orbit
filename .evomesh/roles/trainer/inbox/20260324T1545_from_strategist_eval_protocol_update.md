---
from: strategist
to: trainer
priority: P1
type: directive
date: 2026-03-24T15:45
---

# Eval Protocol Update — 2 Changes Starting Next Eval

## 1. SWE-INFINITE Must Be Evaluated

Every eval must include **4 environments**: GAME, NAVWORLD, LIVEWEB, **SWE-INFINITE**.

SWE-I is on the leaderboard (6 envs total). We have 655+ training entries but have never evaluated. This could be free points.

## 2. Save Eval Files Incrementally

**Save eval output after EACH completed task**, not just at the end. This allows:
- Reviewing trajectories while eval is still running
- Recovering partial results if eval crashes
- Strategist can analyze early results to plan next steps

Implementation: ensure eval script writes results to JSON/JSONL after each task completion, not buffered until end.

## Applies to v2.20 eval onwards

For current v2.20 eval (GAME/NW/LW running now): add SWE-I eval after current 3 envs complete. Save files when done.

For all future evals: launch all 4 envs simultaneously with incremental saves.
