---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-22T10:02
---

# CRITICAL: Fix AMAP API key on M2 BEFORE v2.12 eval

## Discovery

ALL NAVWORLD evals on M2 (v2.10, v2.11) ran WITHOUT AMAP API keys.
95% of tool calls returned `INVALID_USER_KEY`. NW scores (11.08, 8.70) are invalid.

## Root Cause

M2 `/root/.env` is missing AMAP keys. M1 has them, M2 does not.

## Fix (MUST do before v2.12 eval)

Add these lines to M2 `/root/.env`:

```
export AMAP_MAPS_API_KEY=f8da77e10334e089a4a5b2ca66273f88
export AMAP_API_KEY=f8da77e10334e089a4a5b2ca66273f88
```

The eval script reads `AMAP_MAPS_API_KEY` (primary) and `AMAP_API_KEY` (fallback).
Both must be set and exported.

## Verification

After adding to .env:
```bash
source /root/.env
echo $AMAP_MAPS_API_KEY  # should print f8da77e10334e089a4a5b2ca66273f88
```

## Also fix on M1

M1 has `AMAP_API_KEY` but NOT `AMAP_MAPS_API_KEY`. Add:
```
export AMAP_MAPS_API_KEY=f8da77e10334e089a4a5b2ca66273f88
```

## v2.12 Eval Pipeline

Training completing ~10:15 UTC. After merge + sglang:
1. Fix .env FIRST
2. `source /root/.env`
3. Verify: `echo $AMAP_MAPS_API_KEY`
4. THEN start eval

## Impact

With working AMAP keys, NW scores should dramatically improve.
This may make v2.12 (or even v2.10/v2.11) significantly better than reported.

## Also: Save eval files

After eval completes, rsync the full eval JSON and log files back to local:
```
rsync -avz /root/logs/eval_v212_*.log /root/logs/eval_*.json user@local:eval/v2.12/
```
