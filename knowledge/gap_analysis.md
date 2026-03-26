# Gap Analysis

**Last updated**: 2026-03-26 06:15 UTC

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
| hex/othello/clobber | 0.00 | 0% | **v9 rule-based think data targeting 15-22%** |

## Confirmed Rules

1. **NO reasoning-parser** — A/B tested, hurts all envs
2. **Checkpoint ~80-85%** — late overfitting confirmed
3. **NW ≥19% of mix** — below → NW collapses
4. **LW single-turn format** — 5.78→17.68, no parser needed
5. **GAME spatial games** — 0% with MCTS stats data, v9 rule-based think approach in progress
6. **LW tools fix** — v2.23 trained on WRONG tool params (text vs selector). Fixed in v2.24 data. GT case-fix verified +22pts (14→36.8). Potential: 42-50

## v2.24 Design

| Env | Count | % | vs v2.23 |
|-----|-------|---|----------|
| GAME | 8623 | 38.7% | -465 (user refined) |
| NW | 3865 | 17.3% | +904, but **BELOW 19% threshold** |
| LW | 9000 | 40.4% | +6373 (single-turn + tools fix) |
| SWE-I | 804 | 3.6% | +38 |
| Total | 22292 | | +6850 |

Key changes: (1) LW expanded to 9000 with tools param fix. (2) GAME user refined to 8623. (3) NW at 17.3% — well below 19% threshold, high risk of regression.

## v2.24 Expected Impact

- **LW**: 17.68 → 30-40+ (tools fix removes distribution shift + GT case-fix)
- **GAME**: 29.70 → ~30 (similar data, user refined)
- **NW**: 42.84 → **likely regression** (17.3% below 19%; v2.23 at 12% → 34.88)
- **SWE-I**: first eval
