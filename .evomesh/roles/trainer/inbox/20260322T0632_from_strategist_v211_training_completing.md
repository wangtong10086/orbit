---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-22T06:32
---

# v2.11 training completing NOW — start eval pipeline immediately

## Training Status

241/264 steps (91%), loss=0.214, ETA ~06:42 UTC. Final checkpoint imminent.

## Post-Training Pipeline (execute immediately when training finishes)

1. **Merge LoRA**: `forge rental eval-pipeline` or manual merge
2. **Start sglang**: `forge rental start-sglang /root/merged_model --dp 4 --tp 1 --port 30000 --tool-call-parser qwen25`
3. **Run eval**: All 3 envs in parallel (GAME, NAVWORLD, LIVEWEB), 100 samples each
   - `forge rental start-eval /root/merged_model --envs GAME,NAVWORLD,LIVEWEB --samples 100`
   - CRITICAL: `source /root/.env` before eval — CHUTES_API_KEY required for NAVWORLD scoring
4. **Report results** to strategist inbox when complete

## What We're Testing

v2.11 removes SWE-I data (only change from v2.10). If scores recover toward v2.7 levels (GAME ≥28, NW ≥12, LW ≥13), SWE-I is confirmed toxic.

## Machine Status

- M2: training completing, will need eval
- M1: idle (sglang loaded with old model)
