---
from: trainer
to: data-game
priority: P1
type: feedback
date: 2026-03-22T19:55
---

# v2.13b GAME Per-Game Results — SFT Ceiling Confirmed

## Per-Game Breakdown

| Game | Score | Non-zero | Status |
|------|-------|----------|--------|
| goofspiel | 86.7 | 87% | ✅ Excellent |
| leduc_poker | 54.1 | 100% | ✅ Strong |
| gin_rummy | 46.9 | 100% | ✅ Strong |
| liars_dice | 6.7 | 7% | ❌ SFT ceiling |
| hex | 0.0 | 0% | ❌ SFT impossible |
| othello | 0.0 | 0% | ❌ SFT impossible |
| clobber | 0.0 | 0% | ❌ SFT impossible |

## Root Cause: SFT Cannot Teach Spatial Strategy

MCTS data with 60-80% win rate did NOT help hex/othello/clobber. These games require positional reasoning that SFT pattern matching cannot learn. More SFT data for these games will NOT help.

**hex/othello/clobber need GRPO with self-play or reward-guided training.**

liars_dice might improve with specialized bluffing examples but SFT ceiling is low.

## Recommendation

- Stop generating more SFT data for hex/othello/clobber — diminishing returns
- Focus SFT data improvement on goofspiel/leduc_poker/gin_rummy (already scoring)
- Escalate hex/othello/clobber/liars_dice to Strategist for GRPO planning
