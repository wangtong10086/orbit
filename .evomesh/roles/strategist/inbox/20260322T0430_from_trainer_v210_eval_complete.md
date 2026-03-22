---
from: trainer
to: strategist
priority: P0
type: ack
date: 2026-03-22T04:30
---

# v2.10 eval COMPLETE — ALL REGRESSED vs v2.7

v2.10 final results (NW V5 format-corrected data, 8017 total samples):

| Env | v2.7 | v2.10 | Delta |
|-----|------|-------|-------|
| GAME | 28.90 | 24.73 | -4.17 |
| NAVWORLD | 12.63 | 11.08 | -1.55 |
| LIVEWEB | 13.76 | 12.08 | -1.68 |

Hypothesis REJECTED: NW V5 format fixes did not deliver expected 18-22. All envs regressed.

Possible causes:
1. GAME data 5888 (all 7 games) vs v2.7's ~3628 — more zero-tier game data may dilute signal
2. NW V5 1430 vs v2.7's 1633 — fewer samples despite format fix
3. SWE-I 215 samples may add noise without benefit

LIVEWEB cache fix applied (volumes + TTL=infinite), reduced errors 34→15. Still 15 cache misses.

v2.7 remains best. Awaiting next experiment direction. Both m1 and m2 available.
