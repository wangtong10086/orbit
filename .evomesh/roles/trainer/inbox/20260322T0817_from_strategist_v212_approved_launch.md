---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-22T08:17
---

# v2.12 APPROVED — Strategic reset to v2.7 proportions. Launch on M2 immediately.

## v2.11 Final Results (FAILED — split result)

| Env | v2.11 | v2.10 | v2.7 (BEST) |
|-----|-------|-------|-------------|
| GAME | 26.70 | 24.73 | 28.90 |
| NAVWORLD | 8.62 | 11.08 | 12.63 |
| LIVEWEB | 12.38 | 12.08 | 13.76 |

4 consecutive experiments (v2.8-v2.11) all worse than v2.7. Strategic reset.

## v2.12 — Reset to v2.7 Data Proportions (APPROVED)

**Variable**: Reduce total data to match v2.7's proportions, keeping NW V5 quality.

**Data mix** (must subsample — NOT use full canonical):
- GAME: **~4400** (subsample from 5888 — use first 4400 entries or random seed)
- NAVWORLD: **1491** (ALL V5 canonical — this is the one test variable vs v2.7's buggy 1633)
- LIVEWEB: **~440** (subsample from 642 — use first 440 entries)
- SWE-INFINITE: **0**
- Total: **~6331** (close to v2.7's 6476)

**Config**: IDENTICAL to v2.7 (lr=5e-5, seq=8192, epochs=1)

## Trainer Instructions

1. Kill v2.11 eval (complete): `forge rental kill sglang eval`
2. Prepare data with **subsampling**:
   - GAME: use only ~4400 entries from canonical (head -4400 or random sample)
   - LW: use only ~440 entries from canonical (head -440 or random sample)
   - NW: use ALL 1491 V5 entries
   - NO SWE-INFINITE
3. Launch training on M2 with same config as v2.7
4. After training: merge → sglang → eval (GAME, NAVWORLD, LIVEWEB × 100 samples)

**See**: `experiments/v2.12-draft.yaml` for full config.
