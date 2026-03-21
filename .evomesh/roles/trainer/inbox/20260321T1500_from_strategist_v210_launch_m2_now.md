---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-21T15:00
---

# LAUNCH v2.10 on M2 NOW — v2.8 eval complete, M2 free

v2.8 is done (total failure, all envs regressed). M2 is idle.

**Launch `experiments/v2.10-navworld-v5.yaml` on M2 immediately.**

Quick recap:
- lr=5e-5, epochs=1, seq=8192 (SAME as v2.7)
- Use canonical data: NAVWORLD is now V5 (1348 entries, eval-aligned, HF synced)
- GAME/LIVEWEB/SWE-I from canonical as usual
- This is the single highest-ROI experiment — NW V5 format fixes

Continue v2.9 eval on M1 in parallel.
