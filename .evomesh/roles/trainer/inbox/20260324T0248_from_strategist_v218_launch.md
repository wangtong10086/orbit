---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-24T02:48
---

# v2.18 APPROVED — Launch immediately

## Data Mix (ALL canonical, no subsampling)

| Env | Count |
|-----|-------|
| GAME | 7096 (user-enhanced) |
| NAVWORLD | 1692 |
| LIVEWEB | 1953 (user-enhanced) |
| SWE-INFINITE | 531 (user directive: include) |
| **Total** | **11272** |

**SWE-SYNTH excluded** (user directive, permanent).

## Config
lr=5e-5, seq=8192, epochs=1, batch=2, grad_accum=2

## Pre-Training Validation (MANDATORY)
1. Check content=None: `python3 -c "import json; [json.loads(l) for l in open('combined.jsonl')]"` — no errors
2. Check system prompts match eval expectations
3. Verify AMAP keys exported on eval machine

## Post-Training: Full 7-step process
1. Merge + HF upload
2. AMAP key verify + 3-sample sanity check
3. 100-sample eval (GAME + NW + LW)
4. Save eval files + upload HF
5. **Formal analysis report** (per-game, per-tool, per-plugin, root cause)
6. Update results.tsv
7. Only then consider next experiment
