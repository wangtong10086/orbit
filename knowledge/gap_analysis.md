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

## v2.5 Results (disappointing)

| Env | v2.5 | v2.4a | Notes |
|-----|------|-------|-------|
| GAME | 24.28 | **26.03** | ❌ regression |
| NAVWORLD | 6.51 | **7.71** | ❌ worse despite more data |
| LIVEWEB | 11.82 | 11.90 | ≈ same |

v2.5 loss=0.288 (abnormally high). All scores below v2.4a. Possible causes: lr=1e-4 too aggressive for 5533 samples at seq=16384, or data quality issue.

## Current: Dual Machine A/B — lr=1e-4 vs 5e-5

| | M2 (v2.6) | M1 (v2.7) |
|---|---|---|
| lr | **1e-4** | **5e-5** |
| seq | 8192 | 8192 |
| data | 6191 | 6204 |
| status | training | approved (pending start) |

Both use seq=8192 (A/B winner) + latest data (~6200). This isolates lr as the variable.

## Action Items
- [ ] v2.6 training + eval (M2)
- [ ] v2.7 training + eval (M1)
- [ ] Compare lr=1e-4 vs 5e-5
- [ ] NAVWORLD GPT-5.4 continuous generation
- [ ] GAME zero-tier: eval parsing fix or GRPO
