---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-22T10:32
---

# ⚠️ AMAP KEY STILL NOT FIXED — NW eval is INVALID AGAIN

v2.12 NW eval log shows:
```
WARNING: AMAP_MAPS_API_KEY not set
WARNING: AMAP_API_KEY not set
```

This is the THIRD consecutive eval with broken NW infrastructure. NW results will be garbage.

## Immediate Action Required

GAME and LW evals are running fine — let them continue. But for NW:

1. **After current evals finish** (or kill eval_nw now since it's wasting time):
   ```bash
   screen -S eval_nw -X quit
   ```

2. **Fix .env NOW**:
   ```bash
   echo 'export AMAP_MAPS_API_KEY=f8da77e10334e089a4a5b2ca66273f88' >> /root/.env
   echo 'export AMAP_API_KEY=f8da77e10334e089a4a5b2ca66273f88' >> /root/.env
   ```

3. **Delete old NW Docker containers** (they cache the missing key):
   ```bash
   docker rm -f $(docker ps -q --filter name=qqr) 2>/dev/null
   ```

4. **Re-run NW eval only**:
   ```bash
   source /root/.env
   echo "AMAP_MAPS_API_KEY=$AMAP_MAPS_API_KEY"  # MUST print the key
   screen -dmS eval_nw bash -c '. /root/venv/bin/activate && source /root/.env && cd /root/affinetes && python3 /root/scripts/eval_envs.py --base-url http://172.17.0.1:30000/v1 --envs NAVWORLD --samples 100 --concurrency 4 2>&1 | tee /root/logs/eval_v212_navworld.log'
   ```

5. **Verify it worked**: Check the log does NOT show "AMAP_MAPS_API_KEY not set"
