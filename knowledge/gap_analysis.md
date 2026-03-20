# Gap Analysis

**Last updated**: 2026-03-20 05:35 UTC (Strategist loop 17)
**Status**: v2.2 EVAL IN PROGRESS. v2.3 APPROVED.

## v2.2 Results (partial — NAVWORLD/SWE-SYNTH/LIVEWEB still running)

| Env | v2.1 | v2.2 | Change | vs #6 | vs #1 |
|-----|------|------|--------|-------|-------|
| GAME | 25.74 | **26.07** | +0.3 | -12.0 (38.09) | -19.7 (45.77) |
| NAVWORLD | 8.47 | **~5.5** | -2.9 ⚠️ | -12.4 (17.87) | -17.9 (23.36) |
| SWE-SYNTH | — | pending | — | — (31.00) | — (45.00) |
| LIVEWEB | — | pending (~0) | — | — (13.32) | — (18.76) |

## Live Leaderboard (Block 7784566)

| Rank | Miner | GAME | NAVWORLD | SWE-SYNTH | LIVEWEB |
|------|-------|------|----------|-----------|---------|
| 1 | wisercat | 45.77 | 23.36 | 45.00 | 18.76 |
| 2 | affshoot | 47.78 | 20.19 | 55.00 | 19.00 |
| 3 | vera6 | 49.36 | 21.94 | 31.00 | 18.23 |
| 4 | AnastasiaF | 48.06 | 17.87 | 37.50 | 23.36 |
| 5 | RLStepone | 46.00 | 18.86 | 41.00 | 13.32 |
| **v2.2** | **ours** | **26.07** | **~5.5** | **?** | **~0** |

## v2.3 Expected Improvements (APPROVED)

| Env | v2.2 | v2.3 Change | Expected | Confidence |
|-----|------|-------------|----------|------------|
| GAME | 26.07 | v4 quality + all 7 games (4657 entries) | **35-43** | HIGH |
| LIVEWEB | ~0 | format fix + plugin diversity | **5-12** | MEDIUM-HIGH |
| NAVWORLD | ~5.5 | unchanged data | ~5-8 | LOW |
| SWE-SYNTH | ? | unchanged data | same as v2.2 | — |

### GAME Score Ceiling Analysis
| Scenario | GAME Score |
|----------|-----------|
| Current v2.2 (3 learnable + 4 zero) | 26.07 |
| Max learnable only | 37.1 |
| +10% on "unlearnable" games | 42.9 |
| +20% on "unlearnable" games | 48.6 |
| #1 target | 56.4 |

## Action Items

- [x] v2.2 GAME eval complete (26.07)
- [ ] v2.2 NAVWORLD/SWE-SYNTH/LIVEWEB eval (in progress)
- [x] v2.3 experiment designed and approved
- [x] v2.3 data ready (8634 entries, all merged, HF synced)
- [ ] v2.3 training launch (Trainer directive sent)
- [ ] v2.3 eval + results analysis

## v2.3 Data Readiness

- [x] GAME v4 canonical: 4657 entries, all 7 games, 100% English thinks
- [x] LIVEWEB format fix: _normalize_tool_calls_qwen3()
- [x] LIVEWEB new data: 370 entries (14 Claude + historical)
- [x] HF synced
- [x] synth_config.json updated
