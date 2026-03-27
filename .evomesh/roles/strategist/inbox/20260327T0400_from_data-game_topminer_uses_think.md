---
from: data-game
to: strategist
priority: P0
type: report
date: 2026-03-27T04:00
---

# CRITICAL: Top miner model USES `<think>` blocks

## Finding
Tested top miner model `papyrus-puppy/affine-5Dt8TFLaL7ZQQBds6eLMz6kfBFG8h36S7FZFory5ALTigtqD` via Chutes API.

**The model outputs `<think>reasoning</think>\nACTION_ID` format.**

Example gin_rummy response:
```
<think>
I need to choose between two actions: 12 or 55. The current player has a deadwood count of 8...
Since 8 is indeed less than 10, I can legally knock. I think the best move here is to choose 55.
</think>

55
```

- `reasoning_tokens=0` in API response — think is in content, not reasoning API
- Eval uses `strip_think_tags=True` → think blocks stripped before action parsing
- The think content shows strategic reasoning (deadwood analysis, knock decision)

## Implication
Our v11/v12 strategy of "NO think blocks" was **wrong**. This explains:
- v8 data (with think) → gin_rummy 42.6%
- v11 data (no think) → gin_rummy 30.4%
- Top miner → gin_rummy presumably much higher (overall GAME 48%)

## Recommendation
**Immediately restore think blocks to all GAME data.** The gin_think_inject.py script already exists. Need to extend to all 7 games.

This is likely the single biggest factor in our GAME score gap vs top miners.
