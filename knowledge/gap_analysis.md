# Gap Analysis

**Last updated**: 2026-03-26 19:30 UTC

## Best Scores & Competitive Position

| Env | Our Best | Model | #1 Competitor | Gap | Rank |
|-----|----------|-------|--------------|-----|------|
| GAME | 29.70 | v2.23 | 50.18 (wisercat) | -20.48 | 7/7 |
| **NW** | **42.84** | v2.21 | 34.86 (EdmondMillion) | **+7.98** | **1/7** |
| **LW** | **27.76** | **v2.25** | 19.35 (luis1027) | **+8.41** | **1/7** |
| SWE-I | never eval'd | — | 9.18 | ? | ? |

## v2.25 Results — LW NEW BEST, NW Near Best

| Env | v2.25 ckpt-400 | v2.23 | Delta |
|-----|---------------|-------|-------|
| GAME valid | 25.26 | 29.70 | -4.44 |
| **NW** | **40.57** | 34.88 | **+5.69** |
| **LW valid** | **27.76** | 17.68 | **+10.08 NEW BEST** |

### GAME Per-Game (v2.25)

| Game | Score | Rate | vs v2.23 |
|------|-------|------|----------|
| goofspiel | 90.91 | 91% | +4.24 |
| leduc_poker | 48.40 | 92% | -6.82 |
| gin_rummy | 36.42 | 100% | -6.20 |
| **liars_dice** | **0.00** | **0%** | **-20.00 COLLAPSED** |
| hex/othello/clobber | 0.00 | 0% | unchanged |

### Root Cause: liars_dice Collapse
v10 changed liars_dice format (raw→structured) + numdice fix + hand-aware bids. One of these changes broke eval compatibility. Need to isolate.

### Checkpoint Timing: 57% optimal (not 80-85%)

| Checkpoint | GAME | NW | LW |
|-----------|------|-----|-----|
| ckpt-300 (43%) | 24.96 | 31.04 | 24.50 |
| **ckpt-400 (57%)** | **25.26** | **40.57** | **27.76** |
| ckpt-550 (79%) | 13.14 | 28.32 | 19.84 |

v2.25 overfits much faster than previous versions. 80-85% rule no longer universal — depends on data composition.

## Confirmed Rules (updated v2.25)

1. **NO reasoning-parser** — A/B tested, hurts all envs
2. ~~**Checkpoint 80-85%**~~ — **DISPROVED**: v2.25 optimal at 57%. Test multiple checkpoints.
3. **GAME data quality critical** — buggy data cross-contaminates all envs (v2.24 proved)
4. **LW tools fix validated** — 17.68→27.76 (+57%). Single-turn goto+stop by design.
5. **Final save corruption** — always merge from numbered checkpoint
6. **One variable at a time** — v2.25 changed 13 GAME variables, can't isolate liars_dice regression
7. **NW recovers with good GAME data** — v2.24 (buggy GAME) NW=19.57, v2.25 (v10 GAME) NW=40.57

## v2.26 Priority: Fix liars_dice

liars_dice was 20% in v2.23 (GAME v8 data), 0% in v2.25 (GAME v10 data). Fixing liars_dice alone would add ~3-4 points to GAME score (from ~25 to ~29).

Options (from data-game):
- A: v8 original data + only fix goofspiel points_order (minimal change)
- B: v10 data but only random opponent (remove MCTS mix)
- C: v8 data unchanged (baseline)

Recommended: **Option A** — minimal variable change, isolate goofspiel fix vs liars regression.
