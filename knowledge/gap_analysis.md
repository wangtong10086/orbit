# Gap Analysis

**Last updated**: 2026-03-28 07:00 UTC (Block 7837772)

## Best Scores & Competitive Position

| Env | Our Best | Model | #1 Competitor | Gap | Rank |
|-----|----------|-------|--------------|-----|------|
| GAME | 29.70 | v2.23 | 49.03 (wisercat) | -19.33 | last |
| NW | **42.84** | v2.21 | 39.12 (Sanguineey) | +3.72 | **#1 shrinking** |
| LW | 27.76 | v2.25 | **28.42 (RLStepone)** | -0.66 | **#2 (lost #1)** |
| SWE-I | never eval'd | — | 14.00 (EdmondMillion) | ? | ? |

**Layer coverage**: 4/6 envs → max L4 subsets.

## v2.28 — Full Fine-Tuning (in progress)

First full FT run. ms-swift + ZeRO-3 + 8x H200. 87382 entries, seq=32k.
Key change: 32.8B trainable params (was 84M QLoRA = 380x capacity increase).

Expected impact:
- GAME: 35-45 (full FT capacity for all 7 games including spatial)
- NW: 40-45 (10006 entries, 2.4x expansion)
- LW: 30-38 (full trajectories at 32k, no truncation)
- SWE-I: 5-10 (first eval with 1605 entries)

## Competitor Format Analysis

Top miners: full FT, no think chains, bare action IDs. ~48% GAME total.
Per-game breakdown (UID 94):

| Game | Competitor | Our Best | Gap |
|------|-----------|----------|-----|
| goofspiel | 82.9% | 90.91% | +8.0 |
| hex | **67.0%** | 0% | -67.0 |
| gin_rummy | 54.2% | 36.42% | -17.8 |
| leduc_poker | 46.2% | 48.40% | +2.2 |
| othello | **47.7%** | 0% | -47.7 |
| liars_dice | 29.1% | 20.0% | -9.1 |
| clobber | **18.3%** | 0% | -18.3 |

## Confirmed Rules

1. **Full FT > QLoRA** — 380x parameter capacity, matches competitors
2. **ms-swift > custom scripts** — correct loss masking, tool calls, chat template
3. **NO reasoning-parser** — A/B tested, hurts all envs
4. **seq=32k** — 80% of LW truncated at 8k
5. **No think chains for GAME** — bare action IDs
6. **Never upload HF during training** — caused m3 crash
7. **epochs=1 only** — 2 epochs overfits

## Priority Stack

1. **Complete v2.28 full FT** — first priority, validate full FT approach
2. **GAME spatial games** — 19+ point potential if full FT can learn them
3. **SWE-I eval** — 1605 entries, competitors score 4-14
4. **Reclaim LW #1** — lost by 0.66 points to RLStepone
