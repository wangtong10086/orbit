# Gap Analysis

**Last updated**: 2026-03-20 01:00 UTC (Strategist new session loop 1)
**Status**: v2.2 TRAINING COMPLETE. Awaiting LoRA merge + eval.

## v2.1 Results (baseline)

| Env | Score | Target | Status | vs #1 |
|-----|-------|--------|--------|-------|
| GAME | **25.74** | ≥25 | **PASS** ✅ | -21.2 (wisercat 46.9) |
| NAVWORLD | **8.47** | ≥8 | **PASS** ✅ | -15.5 (wisercat 24.0) |
| SWE-SYNTH | — | ≥10 | not tested | — |
| LIVEWEB | — | ≥15 | not tested | — |

## v2.2 Training Summary

- 162/162 steps, final loss 0.2235 (min 0.1883 at step 140)
- vs v2.1 final loss 0.1557 — v2.2 slightly higher (more data, seq=16384)
- Awaiting merge + eval on ALL 4 envs

## Live Leaderboard (Block 7783363)

| Rank | Miner | GAME | NAVWORLD | SWE-SYNTH | LIVEWEB |
|------|-------|------|----------|-----------|---------|
| 1 | wisercat | 46.94 | 23.99 | 46.00 | 18.95 |
| 2 | affshoot | 48.36 | 20.59 | **55.56** | 19.39 |
| 3 | vera6 | 49.21 | 22.37 | 31.25 | 18.17 |
| 4 | AnastasiaFantasy | 38.44 | 20.67 | 46.46 | 16.11 |
| 5 | RLStepone | 46.52 | 18.40 | 38.38 | 14.11 |
| 6 | EdmondMillion | 43.94 | 19.63 | 41.41 | 13.33 |
| **v2.1** | **ours** | **25.74** | **8.47** | **?** | **?** |

### Key Changes Since Last Check
- **affshoot SWE-SYNTH 44→55.56** — massive jump, now clear #1 in SWE-SYNTH
- Competition stable otherwise, wisercat still overall #1

## Rank-Jump ROI (sorted by impact)

| Priority | Env | Our Score | #6 Score | Gap to #6 | Difficulty |
|----------|-----|-----------|----------|-----------|------------|
| **P0** | NAVWORLD | 8.47 | 19.63 | -11.2 | HIGH — need 2.3x improvement |
| **P1** | GAME | 25.74 | 43.94 | -18.2 | HIGH — structural zeros drag avg |
| **P2** | SWE-SYNTH | ? | 31.25 | ? | UNKNOWN — first eval pending |
| **P3** | LIVEWEB | ? | 13.33 | ? | UNKNOWN — tool_call fix may help |

## v2.2 Expected Outcomes

| Env | v2.1 | v2.2 Change | Expected | Rationale |
|-----|------|-------------|----------|-----------|
| NAVWORLD | 8.47 | Claude QQR data, -465 bad | 12-18 | 10x quality improvement in training data |
| GAME | 25.74 | +168 entries | 26-32 | Marginal data add, same games |
| SWE-SYNTH | ? | seq 8192→16384 | 10-25 | 3x more entries now fit in context |
| LIVEWEB | ? | tool_calls restored | 5-15 | Was broken before, now real actions |

## Action Items

- [x] v2.1 eval complete
- [x] v2.2 training complete (162 steps)
- [ ] v2.2 LoRA merge + sglang deploy (P0 directive sent to Trainer)
- [ ] v2.2 full eval (4 envs, 100 samples each)
- [ ] Analyze v2.2 results → approve v2.3
- [ ] Deploy on-chain (needs user permission)
