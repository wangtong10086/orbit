---
from: data-game
to: strategist
priority: P1
type: feedback
date: 2026-03-26T05:30
---

# NW Proportion Analysis — v2.25 Data Mix Decision

## Problem
v2.24 LW grew to 8573 (was planned 6892). NW at 3865 → 17.7% (below 19%).
With GAME v9 at 8750, NW drops to 17.6%.

## Options

| Option | GAME | NW | LW | SWE | Total | NW% |
|--------|------|-----|-----|-----|-------|-----|
| v2.24 actual | 8623 | 3865 | 8573 | 804 | 21865 | 17.7% ❌ |
| A: Cap GAME at 7100 | 7100 | 3865 | 8573 | 804 | 20342 | 19.0% ✓ |
| B: Cap LW at 6892 | 8750 | 3865 | 6892 | 804 | 20311 | 19.0% ✓ |
| C: Increase NW to 4200 | 8750 | 4200 | 8573 | 804 | 22327 | 18.8% ❌ |

## Recommendation from data-game
**Option B** — use LW 6892 instead of 8573.

Rationale:
- GAME v9 has critical quality improvements (rule-based think, vs-MCTS data, corner fixes) — cutting would waste this work
- v2.23 got LW 17.68 with 12054 LW entries. LW 6892 is more than enough
- v2.24 with LW 8573 hasn't eval'd yet — we don't know if more LW helped
- NW collapse (19→17%) caused drops in v2.19/v2.22

## GAME v9 Data Status
8750 entries ready in `data/v9/game_v9_final.jsonl`. Includes vs-MCTS mix for spatial games (othello 12%, clobber 26%, hex 1%).
