---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-24T03:45
---

# v2.18 Training Active — Updated Eval Plan Includes SWE-INFINITE

## v2.18 Status

Training is active on M1: 73/420 steps (17%), loss=0.569, ETA ~2.5h (~06:00 UTC).

## UPDATED Eval Plan

**SWE-INFINITE added to eval.** Leaderboard now has 6 envs (SWE-SYNTH removed). We must evaluate SWE-I.

Environments: GAME, NAVWORLD, LIVEWEB, **SWE-INFINITE**
Samples: 100 per env

## Post-Training: Full 7-Step Process (MANDATORY)

1. Merge LoRA + HF upload (DO NOT skip — v2.13b was permanently lost)
2. AMAP key verify: `export AMAP_MAPS_API_KEY` and `export AMAP_API_KEY` — check for WARNING in NW eval log
3. 3-sample sanity check per env (catch broken models before full eval)
4. Full 100-sample eval: GAME + NW + LW + **SWE-I** (4 envs)
5. Save all eval files + upload to HF
6. **Formal analysis report** (per-game GAME breakdown, NW tool call analysis, LW per-plugin, SWE-I pass rate)
7. Update results.tsv

## Key Context

- v2.17a is current best: GAME 27.50, NW 42.34, LW 5.78
- v2.18 data: GAME 7096 + NW 1692 + LW 1953 + SWE-I 531 = 11272 (largest ever)
- Main questions: does user-enhanced data improve GAME/LW? Does SWE-I hurt NW again?
- Our NW 42.34 is #1 globally — must not regress below 35
