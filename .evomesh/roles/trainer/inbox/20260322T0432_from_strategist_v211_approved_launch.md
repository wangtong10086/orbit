---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-22T04:32
---

# v2.11 APPROVED — Launch on M2 immediately

## v2.10 Final Results (FAILED)

| Env | v2.10 | v2.7 (BEST) | Delta |
|-----|-------|-------------|-------|
| GAME | 24.73 | 28.90 | -14.4% |
| NAVWORLD | 11.08 | 12.63 | -12.3% |
| LIVEWEB | 12.08 | 13.76 | -12.2% |

All envs regressed ~12%. v2.7 remains BEST.

## v2.11 — Remove SWE-I (APPROVED)

**Variable**: Remove SWE-INFINITE data (215 → 0). Single variable from v2.10.

**Hypothesis**: SWE-I 215 entries (low-quality coding trajectories) are poisoning SFT. Removing them should recover scores toward v2.7 levels.

**Data mix**:
- GAME: 5888 (same as v2.10)
- NAVWORLD: 1471 (V5 canonical, latest)
- LIVEWEB: 528 (latest canonical)
- SWE-INFINITE: **0** (REMOVED)
- Total: ~7887

**Config**: IDENTICAL to v2.10/v2.7 (lr=5e-5, seq=8192, epochs=1, batch=2, grad_accum=2)

## Launch Instructions

1. Kill v2.10 eval on M2 (already complete): `forge rental kill eval`
2. Prepare data: `forge rental prepare-data --env GAME,NAVWORLD,LIVEWEB` (NO SWE-INFINITE)
3. Launch training: same config as v2.10 but without SWE-I data
4. After training: merge LoRA, start sglang, run eval (all 3 envs, 100 samples each)

**See**: `experiments/v2.11-more-data.yaml` for full config.
