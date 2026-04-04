# v2.13b Eval Analysis

> Status: Archived evaluation report
> Authority: Non-normative
> Last reviewed: 2026-04-04
> Use this file as a historical result record, not as a current specification.


## Summary

| Env | Score | Errors | vs v2.7 |
|-----|-------|--------|---------|
| GAME | 28.14 | 0/100 | -0.76 (~same) |
| **NAVWORLD** | **25.13** | **0/100** | **+12.50 (+99%)** |
| LIVEWEB | 7.79 | 16/100 | -5.97 (no cache) |

## GAME — Per-Game Breakdown

| Game | Mean | N | Non-zero | Rate |
|------|------|---|----------|------|
| goofspiel | 86.7 | 15 | 13/15 | 87% |
| leduc_poker | 54.1 | 14 | 14/14 | 100% |
| gin_rummy | 46.9 | 14 | 14/14 | 100% |
| liars_dice | 6.7 | 15 | 1/15 | 7% |
| hex | 0.0 | 14 | 0/14 | 0% |
| othello | 0.0 | 14 | 0/14 | 0% |
| clobber | 0.0 | 14 | 0/14 | 0% |

### Why GAME Scores (42/100 = 42% non-zero)

- **goofspiel (86.7)**: Best game. Model learned optimal bidding strategy from MCTS data. 87% win rate.
- **leduc_poker (54.1)**: 100% non-zero. Model bluffs/folds correctly. MCTS data provides strong poker strategy.
- **gin_rummy (46.9)**: 100% non-zero. Model handles meld assignment and draw/discard well.

### Why GAME Doesn't Score (58/100 = 0 score)

- **hex, othello, clobber (0%)**: Despite MCTS training data with 60-80% win rate, the model cannot beat eval MCTS opponents in these spatial/strategic games. The games require deep positional understanding that SFT alone cannot teach.
- **liars_dice (6.7%, 1/15)**: Near-zero. Bluffing/probability game — model occasionally wins but can't consistently deceive.
- **Root cause**: SFT teaches pattern matching, not strategic reasoning. Games with simple rules (poker, gin_rummy) benefit from SFT; spatial games (hex, othello, clobber) need RL/GRPO.

### GAME Improvement Path

- SFT ceiling for GAME is ~28-31 (only 3/7 games reliably score)
- hex/othello/clobber need GRPO with self-play to learn positional strategy
- liars_dice needs specialized bluffing training data

## NAVWORLD — 25.13 (Historic Best)

- **69% non-zero rate** (69/100 tasks score)
- Score distribution: 4 tasks ≥0.75, 17 at 0.50-0.74, 17 at 0.25-0.49, 31 at 0.01-0.24
- **0 errors** — AMAP API keys working perfectly
- Zero-score tasks (31): shorter duration (129s avg vs 339s for scoring), indicating early failures

### Why NW Scores

- V5 format data matches eval format exactly (Chinese prompts, correct tool schema)
- AMAP API keys enable real map/geocoding data during eval
- content=None fix ensures proper tool_call training
- 69% non-zero rate shows model handles most navigation/tool-calling tasks

### Why NW Doesn't Score (31/100)

- Complex multi-step navigation chains where model loses context
- Some tasks require very specific geographic knowledge
- Shorter task duration (129s vs 339s) suggests model gives up early or makes wrong first move

## LIVEWEB — 7.79 (Invalid — No Cache)

- 16/100 errors (all cache_error: HTTP 404, CAPTCHA)
- m1 has no LIVEWEB cache directory — needs re-eval on m2 with cache
- Not comparable to v2.7's 13.76 which had cache

## Conclusions

1. **v2.13b is the new best model** — NW +99%, GAME holds steady
2. **GAME SFT ceiling confirmed at ~28-31** — need GRPO for hex/othello/clobber
3. **NW breakthrough from 3 combined fixes**: AMAP keys, content=None, V5 format
4. **LIVEWEB needs re-eval** on m2 with cache for fair comparison
