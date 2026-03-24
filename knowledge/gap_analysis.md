# Gap Analysis

**Last updated**: 2026-03-24 03:30 UTC

## Training History (v2.1 → v2.17)

| Ver | GAME | NAVWORLD | LIVEWEB | Loss | Data | Key Finding |
|-----|------|----------|---------|------|------|-------------|
| v2.1 | 25.74 | 8.47† | — | 0.156 | 6894 | Baseline |
| v2.4a | 26.03 | 7.71† | 11.90 | 0.231 | 5120 | seq=8192 wins GM |
| **v2.7** | **28.90** | **12.63** | **13.76** | 0.348 | 6204 | **lr=5e-5 — BEST GAME/LW** |
| v2.8 | 24.71 | 6.60 | 4.00 | 0.170 | 6691 | epochs=2 FAILED |
| v2.13b | 28.12 | 25.13 | 11.03 | 0.282 | 6852 | NW +99% (content=None fixed) |
| v2.14 | 25.71 | 6.27 | 13.97 | 0.294 | 5887 | LW best but NW collapsed |
| v2.16 | 26.75 | 35.46 | 6.49 | 0.204 | 9266 | NW +41% (v12 think-then-act) |
| **v2.17a** | **27.50** | **42.34** | **5.78** | — | 8401 | **NW ALL-TIME BEST. No SWE-I.** |
| v2.17b | 29.72 | 35.48 | 4.17 | — | 8775 | SWE-I helps GAME, hurts NW/LW |

**Best per env**: GAME 29.72 (v2.17b), NW **42.34** (v2.17a), LW 13.97 (v2.14)

## Live Leaderboard (Block 7812719) — 6 Environments

**SWE-SYNTH removed from leaderboard.** Now 6 environments, down from 7.

| Rank | Miner | GAME | LGC-v2 | LIVEWEB | NAVWORLD | PRINT | SWE-I |
|------|-------|------|--------|---------|----------|-------|-------|
| 1 | wisercat | 47.56 | 92.37 | 15.68 | 30.58 | 79.79 | 6.32 |
| 2 | papyrus-puppy | 44.11 | 93.98 | 17.86 | 35.46 | 78.00 | 4.30 |
| 3 | vera6 | 47.54 | 91.97 | 16.85 | 24.91 | 80.00 | 4.40 |
| 4 | AnastasiaF | 40.56 | 82.73 | 19.01 | 25.92 | 77.89 | 7.37 |
| 5 | emglab-ai | 42.99 | 89.56 | 17.15 | 35.53 | 77.32 | 5.32 |
| 6 | luis1027 | 48.08 | 96.71 | 18.49 | 27.77 | 82.35 | 5.56 |
| **ours best** | — | **29.72** | **—** | **13.97** | **42.34** | **—** | **—** |

## Competitive Position by Environment

### NAVWORLD — **#1 GLOBALLY** (42.34 vs best 35.53)
Our v2.17a NW 42.34 beats ALL competitors. This is our strongest env. Must protect this lead.

### GAME — Large gap (29.72 vs best 48.08, gap=18.36)
Rank 7/7 (below all competitors). SFT ceiling at ~27-30 for 4/7 games scoring. hex/othello/clobber still near 0%. GRPO needed for spatial games.

### LIVEWEB — Moderate gap (13.97 vs best 19.01, gap=5.04)
Rank 7/7 but closer. Think-then-act pattern causes navigation loops (-41% from v2.13b→v2.16). Needs adversarial recovery training data.

### SWE-INFINITE — Not evaluated yet (0 vs best 7.37)
531 canonical entries in training. Never evaluated our model on this env. Competitors at 4-13. Could be free points.

### LGC-v2 — User excluded (competitors 82-97)
### PRINT — User excluded (competitors 78-82)

## Rank-Jump ROI Analysis

With 6 environments, L6 (all 6) = 32x L1 weight. Missing LGC-v2 and PRINT caps us at L4 max.

| Priority | Env | Action | Expected Impact |
|----------|-----|--------|----------------|
| **CRITICAL** | GAME | GRPO for spatial games | 29→40+ would jump 3-4 ranks |
| **HIGH** | SWE-I | Evaluate current model | Free rank if we score >0 |
| **HIGH** | LW | Fix nav loops (adversarial data) | 14→18 would match mid-pack |
| **PROTECT** | NW | Don't regress below 35 | Already #1 |
| **BLOCKED** | LGC-v2/PRINT | User excluded | Would unlock L6 |

## Current: v2.18 Training (53/420 steps)

Data: GAME 7096 + NW 1692 + LW 1953 + SWE-I 531 = 11272 (largest ever)
Hypothesis: User-enhanced GAME/LW data + SWE-I → improve GAME + LW, hold NW.
Risk: SWE-I hurts NW (A/B showed -16%), but user directive says include.

## Confirmed Findings

1. **lr=5e-5 > lr=1e-4** — v2.7 vs v2.6
2. **seq=8192 > seq=16384** — for overall GM
3. **epochs=1 only** — epochs=2 overfits (v2.8)
4. **Data volume matters** — removing data always hurts (v2.9)
5. **SWE-I trade-off** — helps GAME +8%, hurts NW -16%, hurts LW -48% (v2.17 A/B)
6. **Think-then-act cross-training** — NW +41% from GAME v12 data (v2.16)
7. **AMAP key was NW bottleneck** — v2.10/v2.11 scores invalid
8. **content=None kills model** — must validate before training
9. **User-directive: include SWE-I** — despite A/B showing net negative
10. **User-directive: exclude SWE-SYNTH** — permanent
