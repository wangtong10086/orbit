# Gap Analysis

**Last updated**: 2026-03-19 16:00 UTC (Strategist loop 95)
**Status**: v2.1 EVAL COMPLETE. v2.2 ready for approval.

## v2.1 Results

| Env | Score | Target | Status | vs #1 |
|-----|-------|--------|--------|-------|
| GAME | **25.74** | ≥25 | **PASS** ✅ | -21.5 (wisercat 47.3) |
| NAVWORLD | **8.47** | ≥8 | **PASS** ✅ | -15.3 (wisercat 23.8) |
| SWE-SYNTH | — | ≥10 | not tested | — |
| LIVEWEB | — | ≥15 | not tested | — |

### GAME Per-Game Breakdown

| Game | Score | Non-zero | Data Count | Assessment |
|------|-------|----------|------------|------------|
| goofspiel | **80.0** | 12/15 | 1050 | STRONG |
| gin_rummy | **48.7** | 14/14 | 780 | STRONG — D7 working |
| leduc_poker | **42.3** | 13/14 | 428 | STRONG |
| liars_dice | 6.7 | 1/15 | 333 | WEAK |
| othello | 0.0 | 0/14 | 12 | ZERO — data insufficient |
| hex | 0.0 | 0/14 | 190 | ZERO — SFT-unlearnable? |
| clobber | 0.0 | 0/14 | 123 | ZERO — SFT-unlearnable? |

### NAVWORLD

- Mean 8.47, non-zero 55/100, max 41.6%
- D8 diversity: 5.7 → 8.47 (+48%)
- Code-score only. v2.2 Claude data should push higher.

## Live Leaderboard (Block 7779610)

| Rank | Miner | GAME | NAVWORLD | SWE-SYNTH | LIVEWEB |
|------|-------|------|----------|-----------|---------|
| 1 | wisercat | 47.26 | 23.79 | 43.00 | 19.09 |
| 2 | affshoot | 49.39 | 17.74 | 44.00 | 19.58 |
| **v2.1** | **ours** | **25.74** | **8.47** | **?** | **?** |

## v2.2 ROI Analysis

| Priority | Env | v2.1 | v2.2 Fix | Expected |
|----------|-----|------|----------|----------|
| **P0** | NAVWORLD | 8.47 | Claude QQR data | 12-16 |
| **P1** | GAME | 25.74 | +168 entries | 28-31 |
| **P2** | SWE-SYNTH | ? | seq=16384 | unknown |
| Maintain | LIVEWEB | ? | +39 entries | unknown |

## Action Items

- [x] v2.1 eval complete
- [ ] v2.2 approval
- [ ] GAME goofspiel+leduc merge
- [ ] Deploy on-chain (needs user permission)
