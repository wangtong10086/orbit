# Gap Analysis

**Last updated**: 2026-03-26 05:00 UTC

## Best Scores & Competitive Position

| Env | Our Best | Model | #1 Competitor | Gap | Rank |
|-----|----------|-------|--------------|-----|------|
| GAME | 29.70 | v2.23 | 50.51 (wisercat) | -20.81 | 7/7 |
| **NW** | **42.84** | v2.21 | 34.88 (EdmondMillion) | **+7.96** | **1/7** |
| LW | 17.68 | v2.23 | 19.02 (luis1027) | -1.34 | ~5/7 |
| SWE-I | never eval'd | — | 9.18 | ? | ? |

## GAME Per-Game (v2.23)

| Game | Score | Rate | Status |
|------|-------|------|--------|
| goofspiel | 86.67 | 87% | Stable |
| leduc_poker | 55.22 | 100% | Stable |
| gin_rummy | 42.62 | 93% | ↑ MCTS working |
| liars_dice | 20.00 | 20% | ↑ recovering |
| hex/othello/clobber | 0.00 | 0% | **SFT ceiling — GRPO needed** |

## Confirmed Rules

1. **NO reasoning-parser** — A/B tested, hurts all envs
2. **Checkpoint ~80-85%** — late overfitting confirmed
3. **NW ≥19% of mix** — below → NW collapses
4. **LW single-turn format** — 5.78→17.68, no parser needed
5. **GAME SFT ceiling ~30** — spatial games unlearnable
6. **LW valid_mean=23.04** when cache works — infra fix → 20+

## v2.24 Design

| Env | Count | % | vs v2.23 |
|-----|-------|---|----------|
| GAME | 8747 | 43.1% | -341 (user refined) |
| NW | 3865 | 19.0% | +904 |
| LW | 6892 | 33.9% | +4265 (single-turn expanded) |
| SWE-I | 804 | 4.0% | +38 |
| Total | 20308 | | +4866 |

Key change: LW expanded to 6892 single-turn. NW at 19.0% — exactly on threshold, risk of regression.
