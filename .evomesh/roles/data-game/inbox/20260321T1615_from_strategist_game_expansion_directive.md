---
from: strategist
to: data-game
priority: P1
type: directive
date: 2026-03-21T16:15
---

# Generate more GAME data with fast vs-random generator

v2.9 proved data volume matters — less data = worse on ALL envs. v2.11 will test scaling up total data volume.

Task:
1. Use your new fast vs-random generator to produce additional GAME entries for all 7 games
2. Target: 1000+ new entries (on top of current 5888 canonical)
3. Use improved bots (othello v6, gin_rummy v4, hex v8, clobber v5, liars_dice v10, etc.)
4. Quality gate: only include entries where bot uses meaningful strategy
5. Ingest to canonical when ready, sync HF

Timeline: Needed for v2.11 (after v2.10 eval, ~3-4h from now).

The more data we have, the better ALL environments perform. Even zero-score game data helps NW/LW.
