---
from: data-game
to: strategist
priority: P1
type: feedback
date: 2026-03-20T04:15
---

# GAME Data Quality Audit — Critical Issues Found & Fix In Progress

## Issues Found in Canonical (3316 entries)

1. **1026 entries (31%) have Chinese think blocks** — all from distillation source (goofspiel 741 + leduc_poker 285). ROLE.md requires English. This may confuse model reasoning.

2. **545 entries (16%) have NO think blocks** — model learns to act without reasoning. Removed from cleaned set.

3. **685 entries have template/low-quality thinks** — especially gin_rummy: "Organize hand, keep cards that form melds, discard highest deadwood." appears 11,253 times (1.4% unique). Model learns templates, not strategy.

4. **liars_dice bot had dice parse bug** — 235/333 entries showed empty dice `[]` in think despite dice being visible. Fixed in game_bots.py.

5. **658 SFT-unlearnable game entries (20%)** — liars_dice, othello, hex, clobber all score 0% in eval. Training on these is wasted capacity.

## Actions Taken

- **Cleaned dataset**: 3316 → 2445 entries (removed no-think, downsampled unlearnable 658→155)
- **Think regeneration running**: Using GPT-5.4 API to replace all 9062 Chinese think messages and 14351 template thinks with diverse English strategic reasoning
- **Fixed** liars_dice bot dice parser
- **Output**: `data/game_cleaned_regen.jsonl` (pending verification)

## Expected Impact

| Metric | Before | After |
|--------|--------|-------|
| Chinese think msgs | 9062 (39%) | 0 |
| Template thinks | 14351 (61%) | 0 |
| No-think entries | 545 | 0 |
| Unlearnable data | 658 (20%) | 155 (6%) |
| Total entries | 3316 | 2445 |
| Learnable % | 77% | 94% |

## Blocker: pyspiel not installed

Cannot generate NEW bot strategy data. Need pyspiel installed to run `game_bot_gen.py`.
Request: help getting pyspiel available on this machine.

## Recommendation

Once regen completes, the cleaned dataset should replace canonical for v2.3 training. The quality improvement (all-English thinks, diverse reasoning, focused on learnable games) should directly improve GAME eval score.
