---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-27T19:00
---

# Kill dry-run NOW, launch real training

Dry-run validated at 220+ steps. ZeRO-3 works, GPU 74/143GB, no OOM. Continuing wastes GPU time.

## Action
1. Kill: `forge remote -m m3 exec "screen -S train -X quit"`
2. Launch real training with batch=2, grad_accum=2, save_steps=50
3. Use ZeRO-3 config (proven working)
4. Use the pre-tokenized data approach from v2 script
