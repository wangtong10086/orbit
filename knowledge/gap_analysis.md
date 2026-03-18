# Gap Analysis

**Last updated**: 2026-03-18
**Status**: BLOCKED — not deployed, no leaderboard position

## Current Position

We are not on the leaderboard. No model deployed. Gap analysis requires:
1. Working Forge CLI (`pip install click` or full dependency install)
2. `forge score --top 10` to get current leaderboard state
3. Deploy v1 model → get our scores → populate table

## Leaderboard Table (to populate after v1 eval)

| Env | Our Score | Our Rank | #1 Score | Gap to #1 | Rank-Jump ROI | Priority |
|-----|-----------|----------|----------|-----------|---------------|----------|
| GAME | — | — | — | — | — | — |
| NAVWORLD | — | — | — | — | — | — |
| SWE-SYNTH | — | — | — | — | — | — |
| LIVEWEB | — | — | — | — | — | — |
| LGC-v2 | — | — | — | — | — | — |
| PRINT | — | — | — | — | — | — |

## Known From Audit (old repo v11 reference)

- GAME: ~22.6 (old eval). Competitors: top ~45-65. Structural ceiling at ~40-50 for SFT.
- NAVWORLD: ~5.7 (old eval). Competitor RLStepone: 33.7 (RL methods). SFT plateau confirmed.
- SWE-SYNTH: never locally evaluated
- LIVEWEB: never locally evaluated

## Strategic Observations (pre-deployment)

1. **We need leaderboard data ASAP** — can't make ROI-based decisions without knowing competitor positions
2. **All-env coverage critical** — L6 subset (all envs combined) is 32x weight of L1. If LGC-v2/PRINT are active envs, we score zero there currently.
3. **SFT ceiling for GAME/NAVWORLD** — audit shows diminishing returns. DPO is the v2-v3 play.
4. **Quick win hypothesis**: even a mediocre model deployed across all active envs may rank competitively due to geometric mean + many competitors having zero-coverage gaps.

## Action Items

- [ ] Trainer: fix Forge CLI, pull leaderboard snapshot
- [ ] Trainer: report which environments are currently active on leaderboard
- [ ] Strategist: populate table after v1 eval completes
- [ ] Strategist: decide LGC-v2/PRINT inclusion for v2 based on leaderboard data
