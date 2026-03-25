# Gap Analysis

**Last updated**: 2026-03-25 13:30 UTC

## v2.23 Final Results (ckpt-550, NO reasoning-parser)

| Env | Score | Valid Mean | Errors | Best Ever? |
|-----|-------|-----------|--------|-----------|
| GAME | **29.70** | 29.70 | 0 | ≈ v2.17b (29.72) |
| NW | 34.88 | 34.88 | 0 | No (v2.21: 42.84) |
| **LW** | **17.68** | 20.17 | 13 | **YES — NEW BEST** |

## GAME Per-Game Breakdown (v2.23)

| Game | N | Score | Rate | Trend |
|------|---|-------|------|-------|
| goofspiel | 15 | 86.67 | 87% | Stable |
| leduc_poker | 14 | 55.22 | 100% | Stable |
| gin_rummy | 14 | 42.62 | 93% | ↑ MCTS working |
| liars_dice | 15 | 20.00 | 20% | ↑ recovering |
| hex | 14 | 0.00 | 0% | SFT ceiling |
| othello | 14 | 0.00 | 0% | SFT ceiling |
| clobber | 14 | 0.00 | 0% | SFT ceiling |

## Confirmed Rules (v2.18-v2.23)

1. **NO reasoning-parser qwen3** — A/B tested, hurts all envs (GAME -4, NW -15, LW -5)
2. **Use checkpoint ~80-85%** — late training (85→100%) degrades all envs by 3-6 points
3. **LW data volume dilutes NW** — v2.23 LW 12054 (48% mix) → NW 34.88. v2.17a LW 1159 (14%) → NW 42.34
4. **LW single-turn format works** — 5.78 → 17.68 (+206%), no parser needed
5. **GAME SFT ceiling ~30** — hex/othello/clobber = structural zero. GRPO required.
6. **LW premature stopping** — single-turn format causes 41% null GT (model stops before visiting all pages)

## v2.24 Design Guidelines

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| LW entries | ≤3000 | Protect NW from dilution |
| NW entries | 2961+ | Maintain NW data signal |
| GAME entries | 9088 | Waiting for new data from user |
| reasoning-parser | **OFF** | Confirmed harmful |
| checkpoint | ~80-85% of total | Late overfitting confirmed |
| SWE-I | include | Need first eval |

## Competitive Position

| Env | Ours | #1 Competitor | Rank |
|-----|------|--------------|------|
| GAME | 29.70 | 50.85 | 7/7 |
| NW | 42.84 (v2.21) | 30.72 | **1/7** |
| LW | 17.68 | 20.26 | 5-6/7 |
| SWE-I | never eval'd | 10.00 | ? |
