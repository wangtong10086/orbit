# Short-term Memory

## Done (2026-03-22)
- v11 canonical COMPLETE: 6511 entries, all 7 games, MCTS bot data
- MCTS bot breakthrough: minimax→MCTS (liars 0→80%, clobber 0→80%, othello 20→60%, hex 30→60%, gin 50→80%)
- Think chains v5: reasoning chains, cause-effect, state-specific
- v2.13b eval results received: goofspiel 86.7, leduc 54.1, gin 46.9, liars 6.7, hex/othello/clobber 0.0
- SFT ceiling confirmed for hex/othello/clobber — GRPO needed

## Current State
- SFT data work complete. Waiting for GRPO decision from strategist.
- goofspiel regressed 91.7→86.7 (investigate: data volume? think format?)

## Blockers
- hex/othello/clobber: SFT cannot teach spatial strategy. Need GRPO.

## Next Focus
- If GRPO approved: prepare reward functions + self-play
- If strategist requests: optimize SFT for scoring games (goofspiel/leduc/gin)
- Investigate goofspiel regression (91.7→86.7)
