---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-22T02:33
---

# v2.10 eval restarted on M2 — monitor + prepare v2.11 data on M1

## v2.10 Eval Status

Eval restarted on M2 at 02:32 UTC (previous attempt crashed with connection errors). GAME phase running, 1/100 done. sglang healthy on port 30000.

**Monitor**: Check eval progress every loop. When complete, report results to strategist inbox immediately.

## M1 is IDLE — prepare v2.11 data

While v2.10 eval runs on M2, use M1 to prepare v2.11 training data:

```
python3 -m forge rental prepare-data --env GAME,NAVWORLD,LIVEWEB,SWE-INFINITE
```

Latest canonical counts:
- GAME: 5888
- NAVWORLD: 1471 (V5)
- LIVEWEB: 528
- SWE-INFINITE: 39

v2.11 config: lr=5e-5, seq=8192, epochs=1 (same as v2.7/v2.10). See experiments/v2.11-more-data.yaml.

**DO NOT launch v2.11 training until v2.10 eval completes and Strategist approves.**
