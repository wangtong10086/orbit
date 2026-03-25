# Gap Analysis

**Last updated**: 2026-03-25 08:30 UTC

## Best Scores Per Environment

| Env | Our Best | Model | Competitor Best | Gap | Rank |
|-----|----------|-------|-----------------|-----|------|
| GAME | 28.21 | v2.20 | 50.85 (wisercat) | -22.64 | 7/7 |
| **NW** | **42.84** | v2.21 | 30.72 (papyrus) | **+12.12** | **1/7** |
| LW | 5.78 (valid: 23.04) | v2.22 | 20.26 (deepresearch) | -14.48 (or -0 valid) | 7/7 |
| SWE-I | never eval'd | — | 10.00 | ? | ? |

## Key Bottlenecks (ranked by ROI)

### 1. LW Cache Fix (infra, no training needed)
- 72/100 errors from stooq cache → valid_mean=23.04
- Fix cache → LW 6→20+. Directive sent to data.

### 2. Reasoning Parser (eval config)
- `--reasoning-parser qwen3` enables thinking across all envs
- v2.23 is first model trained with compatible data

### 3. GAME SFT Ceiling
- hex/othello/clobber = 0% across 5+ versions. **SFT unlearnable. Need GRPO.**
- gin_rummy responds to MCTS data (+8%)
- liars_dice regressed with MCTS data (-20%)

### 4. SWE-I Coverage
- 770+ training entries, never evaluated
- Need Docker config in eval_envs.py

## Confirmed Findings

1. **Qwen3 template drops multi-turn `<think>`** — LW fixed (single-turn), NW safe (tool msgs)
2. **reasoning-parser + tool_call conflict** — model must think before tool_call in training data
3. **Final save corruption** — merge from numbered checkpoint only
4. **content=None kills model** — validated 0 across 349K msgs
5. **GAME/NW trade-off eliminated** — with reasoning-parser + proper data, both should work
