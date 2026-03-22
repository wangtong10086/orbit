---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-22T13:47
---

# v2.13 training completing ~14:02 UTC on M1 — eval pipeline immediately

## v2.12 FINAL (FAILED)

GAME 23.22, NW 10.42, LW 13.12. All below v2.7. 6th consecutive failure.

## v2.13 — Most Important Experiment Yet

v2.13 uses GAME v11 MCTS data (4462 entries, all 7 games with 60-80% win bots).
This is the biggest data quality jump since project start.

Training: 187/221 (85%), completing ~14:02 UTC on M1.

## Eval Pipeline (on M1)

1. Merge LoRA → start sglang on M1
2. **CRITICAL**: `source /root/.env` — verify AMAP keys:
   ```bash
   echo "AMAP_MAPS_API_KEY=$AMAP_MAPS_API_KEY"
   ```
   If missing, add:
   ```bash
   echo 'export AMAP_MAPS_API_KEY=f8da77e10334e089a4a5b2ca66273f88' >> /root/.env
   source /root/.env
   ```
3. Launch all 3 evals in parallel screens (GAME, NAVWORLD, LIVEWEB × 100 samples)
4. **Save ALL eval files** — per new ROLE.md rules:
   - Eval JSON + logs to `/root/logs/eval_v213_*.log`
   - After completion: write analysis report per env
   - rsync to local `eval/v2.13/`
