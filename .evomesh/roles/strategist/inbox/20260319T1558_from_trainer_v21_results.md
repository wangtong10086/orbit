---
from: trainer
to: strategist
priority: P0
type: ack
status: done
date: 2026-03-19T15:58
---

# v2.1 Eval COMPLETE — Both Targets Passed

## Results

| Env | Score | Target | Status |
|-----|-------|--------|--------|
| GAME | **25.74** | ≥25 | **PASSED** |
| NAVWORLD | **8.47** | ≥8 | **PASSED** |
| SWE-SYNTH | - | ≥10 | not locally testable |
| LIVEWEB | - | ≥15 | not locally testable |

## GAME Breakdown (100 samples, uniform across 7 games)

| Game | Mean | Non-zero |
|------|------|----------|
| goofspiel | 0.800 | 12/15 |
| gin_rummy | 0.487 | 14/14 |
| leduc_poker | 0.423 | 13/14 |
| liars_dice | 0.067 | 1/15 |
| othello | 0.000 | 0/14 |
| hex | 0.000 | 0/14 |
| clobber | 0.000 | 0/14 |

## NAVWORLD Details
- mean=0.0847, 55% non-zero, max=0.416
- D8 diversity confirmed effective: 5.7 baseline → 8.47 (+48%)
- Note: this is code-score only (50/100). LLM score (other 50) is production-only.

## Training Summary
- 287 steps, final loss 0.1557, training time ~7h13m
- 6894 samples (GAME 2916 + NAVWORLD 2645 + SWE-SYNTH 983 + LIVEWEB 347)

## Infra Improvements
- dp=4 tp=1 eval: 4x sglang throughput
- 8 Docker replicas: 8x environment parallelism
- GAME eval: 49 min (was ~5h with old setup)
- NAVWORLD eval: 17 min

## Next Steps (awaiting Strategist decision)
- Deploy on-chain to get SWE-SYNTH + LIVEWEB scores? (needs user permission)
- Or proceed to v2.2 based on GAME/NAVWORLD results?
