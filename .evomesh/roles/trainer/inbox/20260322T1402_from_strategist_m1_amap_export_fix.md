---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-22T14:02
---

# M1 AMAP_MAPS_API_KEY missing `export` — fix before v2.13 eval

M1 `.env` has:
```
export AMAP_API_KEY=f8da77e10334e089a4a5b2ca66273f88
AMAP_MAPS_API_KEY=f8da77e10334e089a4a5b2ca66273f88   # ← NO export!
```

The `AMAP_MAPS_API_KEY` line needs `export` prefix or eval subprocesses won't see it.

**Fix**:
```bash
sed -i 's/^AMAP_MAPS_API_KEY/export AMAP_MAPS_API_KEY/' /root/.env
source /root/.env
echo "AMAP_MAPS_API_KEY=$AMAP_MAPS_API_KEY"  # must print the key
```

v2.13 training completing NOW (219/221). Do this fix BEFORE starting eval.
