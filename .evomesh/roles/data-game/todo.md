# Data-Game TODO

## Final v6 Data Generation — MCTS Stats Think + v12 System Prompt

**4 machines: m1 + m2 + work1 + work2**

| Game | Count | Target | Status |
|------|-------|--------|--------|
| goofspiel | 1048 | ✅ | Rule bot think |
| leduc_poker | 1069 | ✅ | Rule bot think |
| liars_dice | 1829 | ✅ | MCTS stats T1 + Rule fallback |
| clobber | 1158 | ✅ | MCTS stats think |
| othello | 304 | 1000 | 🔄 m2+work1+work2 (72 procs) |
| hex | 317 | 1000 | 🔄 m1+m2+work1 (80 procs) |
| gin_rummy | 370 | 1000 | 🔄 m1+m2+work2 (112 procs) |

## Think Chain Architecture (Final)
- MCTS search → extract child stats (visits + win rates)
- If visits > 1: MCTS stats think ("Evaluated N options: a1 (78%)...")
- If visits ≤ 1: fallback to game-specific rule think
- Lookahead: opponent response → our counter (from search tree)
- Game context: corner/bridge/safe capture etc.
- System prompt: v12 (think in `<think>` tags)

## Machines
- m1: gin 64x + hex 32x + liars ✅
- m2: othello 24x + hex 24x + clobber ✅ + gin 16x
- work1: hex 32x + othello 64x
- work2: gin 64x + othello 16x
