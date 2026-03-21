# Gap Analysis

**Last updated**: 2026-03-21 00:00 UTC

## Training History

| Ver | GAME | NAVWORLD | LIVEWEB | Loss | seq | Data | GM |
|-----|------|----------|---------|------|-----|------|----|
| v2.1 | 25.74 | **8.47** | — | 0.156 | 8192 | 6894 | — |
| v2.2 | 26.04 | 6.10 | 6.83 | 0.224 | 16384 | 7239 | ~10.5 |
| v2.3 | 22.69 | 1.52 | 8.62 | 0.172 | 16384 | 7626 | ~5.5 |
| **v2.4a** | **26.03** | **7.71** | 11.90 | 0.231 | **8192** | 5120 | **~13.4** |
| v2.4b | 25.44 | 4.58 | **15.77** | ~0.17 | 16384 | 5278 | ~12.3 |
| v2.5 | pending | pending | pending | 0.288 | 16384 | 5533 | — |

## A/B Test Conclusion (v2.4a vs v2.4b)

**seq=8192 wins on geometric mean** (13.4 vs 12.3) despite lower LIVEWEB.

| Env | seq=8192 | seq=16384 | Winner |
|-----|----------|-----------|--------|
| GAME | 26.03 | 25.44 | 8192 (+0.59) |
| NAVWORLD | **7.71** | 4.58 | **8192 (+3.13)** |
| LIVEWEB | 11.90 | **15.77** | **16384 (+3.87)** |
| **3-env GM** | **13.4** | 12.3 | **8192 wins** |

**Root cause**: seq=8192 preserves NAVWORLD tool-calling quality. seq=16384 packing dilutes short NAVWORLD entries among longer sequences.

**Implication**: v2.6 should use seq=8192 for best overall score.

## Live Leaderboard (Block 7784716)

| Rank | Miner | GAME | NAVWORLD | SWE | LIVEWEB |
|------|-------|------|----------|-----|---------|
| 1 | wisercat | 45.60 | 23.36 | 45.00 | 18.64 |
| 6 | coffie3 | 37.90 | 21.01 | 47.00 | 15.39 |
| **v2.4a** | **ours** | **26.03** | **7.71** | **—** | **11.90** |

## Rank-Jump ROI

1. **NAVWORLD** (7.71 vs #6=21.01, gap=13.3): More GPT-5.4 data (1157→1215 already). seq=8192 helps.
2. **GAME** (26.03 vs #6=37.90, gap=11.9): Zero-tier = eval parsing. Need GRPO or eval fix.
3. **LIVEWEB** (11.90 vs #6=15.39, gap=3.5): seq=16384 helps but hurts NAVWORLD. Need more data instead.
4. **SWE-Infinite**: 22 trajectories ready. Not yet in training.

## v2.6 Recommendation

Use **seq=8192** (v2.4a config) + latest data (NW 1215+):

| Env | v2.4a | v2.6 plan | Change |
|-----|-------|-----------|--------|
| GAME | 3918 | 3918 | — |
| NAVWORLD | 805 | **1215+** | +410 GPT-5.4 |
| LIVEWEB | 397 | **400+** | growing |
| SWE-Infinite | 0 | **22** | NEW |
| **Total** | 5120 | **~5555** | +435 |

Expected: NAVWORLD 9-11 (more data at seq=8192), LIVEWEB ~12 (stable), GAME ~26.

## Action Items
- [ ] v2.5 eval (M2, pending)
- [ ] v2.6 design (seq=8192 + latest data + SWE-Infinite 22 trajectories)
- [ ] NAVWORLD GPT-5.4 continuous generation
- [ ] GAME zero-tier: eval parsing fix or GRPO
