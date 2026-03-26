# Short-term Memory

## Current State (2026-03-26)
- v9 data strategy designed and documented in knowledge/environments/GAME.md
- All 5 bots fixed (liars v4, gin v3, othello v6, clobber v6, hex v9)
- Core change: ALL bots now use rule-based IF-THEN think chains, not MCTS stats
- Bot fixes committed and pushed to main

## v9 Generation Status
- liars_dice: ~1800 target, generating fast (~1200/5min)
- clobber: ~1200 target, generating (~100/5min)
- othello: ~1500 target, generating slowly (~8/5min, MCTS bottleneck)
- hex: ~2000 target, generating slowly (~5/5min, MCTS bottleneck)
- gin_rummy: ~1500 target, generating very slowly (~1/5min, MCTS+long games)
- goofspiel/leduc: keep current v8 data (no regeneration needed)

## Key Bot Fixes (from v2.23 eval trajectory analysis)
1. liars_dice: model memorized "5-5" opening → hand-aware bid clamp + call-liar override
2. gin_rummy: model never knocked → always-knock-when-eligible override
3. othello: model ignored corners → corner priority + corner scan prefix + X-square avoidance
4. clobber: model captured greedily → mobility report in every think chain
5. hex: model played horizontal lines → goal direction prefix ("connect top-to-bottom")
6. ALL: switched from MCTS stats think to rule-based IF-THEN think chains

## Bot Test Results
- liars_dice v4: 2W 3L (40% vs eval-level MCTS, up from ~20%)
- othello/gin/hex/clobber: tests running on GPU

## Blockers
- hex/othello generation is very slow (MCTS computation per turn)
- gin_rummy generation extremely slow
- May need to run for many hours or find ways to parallelize

## Next Focus
- Monitor generation progress
- Quality-check generated data samples
- When generation complete: merge into canonical, coordinate with Data Agent
- Report to Strategist with v9 data plan and NW 19% constraint
