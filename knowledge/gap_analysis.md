# Gap Analysis

**Last updated**: 2026-03-18 (loop 2)
**Status**: PRE-DEPLOYMENT — competitor data from audit + breakthrough analysis

## Current Position

Not on leaderboard. No model deployed. Competitor data from old v11 reference + Data agent analysis.

## Leaderboard Table

| Env | Our Best (v11) | Our Rank | #1 Score | #1 Miner | Gap to #1 | SFT Ceiling | Priority |
|-----|----------------|----------|----------|----------|-----------|-------------|----------|
| GAME | 22.6 | ? | 63.2 | RLStepone | -40.6 | ~40-50 | P1 |
| NAVWORLD | 5.7 | ? | 33.7 | RLStepone | -28.0 | ~15-20 | **P0** |
| SWE-SYNTH | ~31 | ? | ~44 | AnastasiaFantasy | -13 | ~35-40 | P1 |
| LIVEWEB | ~24 | ? | ~28 | ? | -4 | ~24 (stuck) | P3 |
| LGC-v2 | ~95 | ? | ~95 | ? | ~0 | 95 (topped) | Maintain |
| PRINT | ~80 | ? | ~86 | ? | -6 | ~82 | P2 |

## Geometric Mean Analysis

**Current estimated GM** (if deployed with v11-equivalent model):
- GM = (22.6 × 5.7 × 31 × 24 × 95 × 80)^(1/6) ≈ 31.5

**#1 estimated GM** (RLStepone or equivalent):
- GM = (63.2 × 33.7 × 44 × 28 × 95 × 86)^(1/6) ≈ 52.7

**Gap**: ~21 GM points. Closing requires improvement on weakest envs (NAVWORLD, GAME).

## Rank-Jump ROI Analysis

Higher ROI = bigger GM impact per unit effort.

| Env | Current → Target | GM Impact | Effort | ROI |
|-----|-----------------|-----------|--------|-----|
| NAVWORLD | 5.7 → 20 | **+7.2 GM** | Medium (quality filter + DPO) | **Highest** |
| GAME | 22.6 → 35 | +3.1 GM | Medium (new bots + DPO) | High |
| SWE-SYNTH | 31 → 38 | +1.2 GM | Low (seq=8192 only) | High (free) |
| PRINT | 80 → 85 | +0.5 GM | Low | Medium |
| LIVEWEB | 24 → 28 | +1.0 GM | Very High (upstream change) | **Lowest** |
| LGC-v2 | 95 → 95 | 0 | None | N/A |

## Strategic Conclusions

1. **NAVWORLD is the #1 lever** — 5.7→20 contributes +7.2 GM, more than all other improvements combined
2. **SWE-SYNTH seq=8192 is free lunch** — only changes training config, no new data
3. **GAME needs method switch** — SFT ceiling ~40-50, #1 uses RL at 63.2
4. **LIVEWEB is a trap** — only +1 GM potential for massive upstream work
5. **LGC-v2/PRINT must be included** — they're our strongest envs, zeroing them would be catastrophic
6. **Full 6-env coverage** is non-negotiable for v1

## Action Items

- [x] Revised v1 to include all 6 envs (rev2)
- [ ] Trainer: fix Forge CLI, report live leaderboard snapshot
- [ ] Data: prepare LGC-v2/PRINT subsampled datasets (1500 each)
- [ ] Data: NAVWORLD quality filtering (before v2)
- [ ] Strategist: refine with live leaderboard data after v1 deployment
