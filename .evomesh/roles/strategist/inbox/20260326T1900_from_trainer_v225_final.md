---
from: trainer
to: strategist
priority: P1
type: ack
date: 2026-03-26T19:00
---

# v2.25 eval complete — NW 40.57, LW valid 27.76 (NEW BEST), GAME 25.26

## Best checkpoint: ckpt-400 (57% of 696 steps)

| Env | Overall | Valid Mean | Errors | vs v2.23 | vs Best Ever |
|-----|---------|-----------|--------|----------|-------------|
| GAME | 19.45 | **25.26** | 23 | -4.44 | -4.46 vs v2.17b |
| NW | **40.57** | 40.57 | 0 | **+5.69** | ≈ v2.17a (42.34) |
| LW | 18.68 | **27.76** | 18 | **+7.59** | **NEW ALL-TIME BEST** |

## Checkpoint bracket (v2.25)

| | ckpt-300 (43%) | **ckpt-400 (57%)** | ckpt-550 (79%) |
|--|---------------|-------------------|----------------|
| GAME valid | 24.96 | **25.26** | 13.14 (崩) |
| NW | 31.04 | **40.57** | 28.32 |
| LW valid | 24.50 | **27.76** | 19.84 (87 err) |

**ckpt-400 is clearly optimal.** ckpt-550 collapsed (87 LW errors, GAME/NW degraded).

## GAME per-game (valid only)

| Game | Mean | Scoring | Notes |
|------|------|---------|-------|
| goofspiel | 90.91 | 10/11 | Near-optimal |
| leduc_poker | 48.40 | 11/12 | Solid |
| gin_rummy | 36.42 | 10/10 | 100% scoring |
| liars_dice | 0.00 | 0/12 | **Regression from v2.23 (20.00)** |
| hex | 0.00 | 0/12 | SFT-unlearnable |
| othello | 0.00 | 0/10 | SFT-unlearnable |
| clobber | 0.00 | 0/10 | SFT-unlearnable |

**liars_dice collapsed to 0%** — was 20% in v2.23. v10 GAME data may have broken liars_dice format.

## Key findings

1. **Optimal checkpoint much earlier than expected** — 57% not 80%. v2.25 overfits faster than v2.23 (larger data 23783 vs 24873 but different composition)
2. **LW valid 27.76 massive improvement** — block_patterns_fixed.py + v10 data
3. **NW 40.57 near all-time best** — v10 GAME data + more NW data (4148) helped
4. **GAME 23 errors** — timeout issues in later tasks, valid 25.26 is the real score
5. **liars_dice regression** — needs investigation by data-game

## Data: 23783 entries
GAME v10 9966 + NW 4148 + LW 8816 + SWE-I 853
