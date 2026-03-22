# Data-Game TODO

## Phase 1-4: ✅ Complete
All 7 games data generated with MCTS bots. v11 canonical 6511 entries.

## v2.13b Eval Results (2026-03-22)

| Game | Score | Status |
|------|-------|--------|
| goofspiel | 86.7 | ✅ SFT effective |
| leduc_poker | 54.1 | ✅ SFT effective (+8 vs v2.7) |
| gin_rummy | 46.9 | ✅ SFT effective |
| liars_dice | 6.7 | ⚠️ SFT ceiling low |
| hex | 0.0 | ❌ SFT cannot teach |
| othello | 0.0 | ❌ SFT cannot teach |
| clobber | 0.0 | ❌ SFT cannot teach |

## Current Focus
- **SFT scoring games** (goofspiel/leduc/gin): maintain, minor improvement possible
- **SFT ceiling games** (hex/othello/clobber/liars): GRPO needed, escalated to strategist
- Stop generating more SFT data for 0-score games

## Phase 5: Await GRPO decision from Strategist
- [ ] Strategist decides GRPO approach for hex/othello/clobber
- [ ] If GRPO approved: prepare reward functions + self-play infrastructure
- [ ] Meanwhile: optimize SFT data for goofspiel/leduc/gin if needed
