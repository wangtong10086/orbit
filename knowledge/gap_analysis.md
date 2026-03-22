# Gap Analysis

**Last updated**: 2026-03-22 11:47 UTC

## Training History

| Ver | GAME | NAVWORLD | LIVEWEB | Loss | Data | Key Finding |
|-----|------|----------|---------|------|------|-------------|
| v2.1 | 25.74 | 8.47† | — | 0.156 | 6894 | Baseline |
| v2.4a | 26.03 | 7.71† | 11.90 | 0.231 | 5120 | seq=8192 wins GM |
| v2.6 | 26.66 | 5.82† | 11.73 | 0.301 | 6191 | lr=1e-4 control |
| **v2.7** | **28.90** | **12.63** | **13.76** | 0.348 | 6204 | **lr=5e-5 — BEST GAME/LW** |
| v2.8 | 24.71 | 6.60 | 4.00 | 0.170 | 6691 | epochs=2 FAILED |
| v2.9 | 26.48 | 8.36 | 6.42 | 0.266 | 5413 | Less data = worse |
| v2.10 | 24.73 | 11.08⚠️ | 12.08 | — | 8017 | ⚠️ NW score invalid (AMAP key missing) |
| v2.11 | 26.17 | 8.70⚠️ | 12.37 | 0.329 | 8021 | ⚠️ NW invalid. SWE-I removal helped GAME. |
| v2.12 | 23.22 | 10.42 | 13.12 | 0.332 | 5637 | v2.7 proportions + AMAP fixed. All below v2.7. |
| **v2.13** | **~0** | **0.00** | **—** | 0.277 | 6852 | **TOTAL FAILURE** — MCTS data destroyed model. NW 100/100 zeros. |

†v2.1-v2.6 NW code-only (max 50). v2.7+ CHUTES LLM scoring (max 100).
⚠️ AMAP API key missing on M2 — NW tool calls failed, scores invalid.

## CRITICAL DISCOVERY: AMAP API Key Was Missing (2026-03-22)

v2.10 and v2.11 NW evals ran WITHOUT AMAP API keys on M2. 95% of tool calls returned `INVALID_USER_KEY`. **All NW scores from v2.10 (11.08) and v2.11 (8.70) are invalid.** The "NW collapse" and "V5 didn't help" conclusions were WRONG — they were measuring broken infrastructure, not model capability.

Fixed in v2.12 eval. v2.12 NW at **15.47 (55/100)** — first valid measurement with working AMAP, already +22% over v2.7.

## Live Leaderboard (Block 7798081) — 7 Environments

| Rank | Miner | GAME | LGC-v2 | LIVEWEB | NAVWORLD | PRINT | SWE-I | SWE-SYNTH |
|------|-------|------|--------|---------|----------|-------|-------|-----------|
| 1 | affshoot | 47.06 | 89.56 | 20.81 | 27.92 | 82.72 | 12.37 | 46.39 |
| 2 | AnastasiaF | 46.51 | 90.00 | 22.71 | 18.68 | 83.60 | 12.00 | 25.00 |
| 3 | wisercat | 46.54 | 89.07 | 18.89 | 27.93 | 82.29 | 8.00 | 29.00 |
| 4 | vera6 | 48.52 | 88.00 | 17.94 | 25.04 | 87.23 | 10.20 | 25.00 |
| 5 | RLStepone | 45.53 | 90.40 | 14.76 | 24.43 | 83.94 | 9.09 | 26.26 |
| v2.12 | ours | 23.22 | — | 13.12 | 10.42 | — | — | — |

We cover 3/7 environments. Missing 4 envs (LGC-v2, PRINT, SWE-I, SWE-SYNTH) with L7=64x L1 weight is catastrophic.

## Rank-Jump ROI (sorted by impact)

### Tier 0: Environment Coverage (HIGHEST PRIORITY)
- **SWE-INFINITE** (0 vs #6=8.08): 126 trajectories canonical. Competitors 8-12.
- **SWE-SYNTH**: Replaced by SWE-INFINITE. Competitors 25-46.
- **LGC-v2**: User excluded. Competitors 80-90.
- **PRINT**: User excluded. Competitors 82-87.

### Tier 1: Existing Environment Improvement
1. **GAME** (28.90 vs #6=37.88, gap=8.98): **v11 MCTS data ready** — all 7 games with 60-80% win bot data (4462 entries). Previously only 3/7 scored. Highest-ROI experiment for v2.13.
2. **NAVWORLD** (~15.5 vs #6=24.24, gap=8.74): V5 data + working AMAP. First valid eval shows +22% over v2.7. Room to improve with more data.
3. **LIVEWEB** (13.12 vs #5=14.76, gap=1.64): Close to rank 5. 754 entries canonical.

## Confirmed Findings

1. **lr=5e-5 > lr=1e-4** — v2.7 vs v2.6 A/B
2. **seq=8192 > seq=16384** — for overall GM
3. **epochs=1 only** — epochs=2 causes overfitting (v2.8)
4. **Data volume matters** — removing data always hurts (v2.9)
5. **SWE-I is toxic** — 215 entries hurt GAME/LW (v2.10 vs v2.11)
6. **Data proportions matter** — v2.7 had GAME 59%, NW 26%, LW 15%. Deviation hurts.
7. **AMAP key was the NW bottleneck** — not V5 data, not proportions. Fixed in v2.12.

## v2.12 EVAL IN PROGRESS

- **Data**: GAME 3400 (60%) + NW 1547 (27%) + LW 690 (12%) = 5637 (v2.7 proportions)
- **Config**: lr=5e-5, seq=8192, epochs=1 (same as v2.7)
- **AMAP key**: FIXED on M2

| Env | v2.12 (partial) | v2.7 | Delta | Samples |
|-----|----------------|------|-------|---------|
| GAME | ~13.4 | 28.90 | — | 35/100 (too early) |
| **NAVWORLD** | **~15.5** | 12.63 | **+22%** | **55/100 (reliable)** |
| LIVEWEB | **13.12** | 13.76 | -4.6% | FINAL (15 errors) |

## Action Items
- [x] v2.12 EVAL COMPLETE — GAME 23.22, NW 10.42, LW 13.12. All below v2.7. FAILED.
- [x] v2.13 EVAL — **TOTAL FAILURE**. NW=0.00 (100/100), GAME 0 completed in 52 min. MCTS v11 data format is broken.
- [ ] **URGENT**: Investigate v11 MCTS data format — does it match eval action format? Think tag closing? Action parsing?
- [ ] GAME GRPO framework (Phase 3 — data-game in Phase 1 bot optimization)
- [ ] SWE-INFINITE scale-up (126→200+ trajectories)
- [ ] **FLAG TO USER**: LGC-v2 + PRINT exclusion is strategically costly with 7-env leaderboard
- [ ] v2.7 NW re-eval needed with fixed AMAP key (was M1 AMAP_MAPS_API_KEY set?)
