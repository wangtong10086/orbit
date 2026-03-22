---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-22T22:02
---

# AMAP keys need `export` on M2 — NW eval BROKEN AGAIN (4th time!)

## Root Cause (finally identified)

M2 `.env` has the keys BUT WITHOUT `export`:
```
AMAP_API_KEY=f8da77e10334e089a4a5b2ca66273f88      # ← missing export
AMAP_MAPS_API_KEY=f8da77e10334e089a4a5b2ca66273f88  # ← missing export
```

Without `export`, variables are local to the current shell and NOT inherited by subprocesses (eval scripts, Docker containers).

## Permanent Fix

```bash
sed -i 's/^AMAP_API_KEY/export AMAP_API_KEY/' /root/.env
sed -i 's/^AMAP_MAPS_API_KEY/export AMAP_MAPS_API_KEY/' /root/.env
```

Then verify:
```bash
source /root/.env
env | grep AMAP  # must show both keys
```

## After Fix: Kill and restart NW eval only

```bash
screen -S eval_nw -X quit
docker rm -f $(docker ps -q --filter name=qqr) 2>/dev/null
source /root/.env
screen -dmS eval_nw bash -c '. /root/venv/bin/activate && source /root/.env && cd /root/affinetes && python3 /root/scripts/eval_envs.py --base-url http://172.17.0.1:30000/v1 --envs NAVWORLD --samples 100 --concurrency 4 2>&1 | tee /root/logs/eval_v214_navworld.log'
```

GAME and LW evals are fine — let them continue.
