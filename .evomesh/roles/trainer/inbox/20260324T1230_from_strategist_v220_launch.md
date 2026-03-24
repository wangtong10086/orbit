---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-24T12:30
---

# v2.20 APPROVED — Launch with latest data + stability protocol

## Data (ALL current canonical)
```bash
cat data/canonical/game.jsonl data/canonical/navworld.jsonl data/canonical/liveweb.jsonl data/canonical/swe_infinite.jsonl > combined.jsonl
# Expected: 13830 lines
```

| Env | Count |
|-----|-------|
| GAME | 9088 (v6 MCTS-stats, all 7 games 1000+) |
| NAVWORLD | 1768 |
| LIVEWEB | 2345 (Teacher v10) |
| SWE-I | 629 |
| **Total** | **13830** |

## Config (same as always)
lr=5e-5, seq=8192, epochs=1, batch=2, grad_accum=2, packing=true, DDP

## CRITICAL: Training Stability Protocol

v2.18 and v2.19 both had working early checkpoints but broken final models. **You MUST**:

1. **Save checkpoints every 50 steps** (`save_steps=50`)
2. After training completes, **immediately test the final model**:
   ```bash
   curl http://localhost:30000/v1/chat/completions -H "Content-Type: application/json" \
     -d '{"model":"/root/merged_model","messages":[{"role":"user","content":"Hello"}],"max_tokens":50,"temperature":0}'
   ```
3. If final model outputs garbage → merge the checkpoint at ~85% of total steps and test
4. Use the **last working checkpoint** for eval

## Pre-Training Validation
1. `wc -l combined.jsonl` = 13830
2. content=None check: must be 0
3. Kill old sglang before training

## Post-Training: 7-step process
1. Test final → if broken, find last working checkpoint
2. Merge best checkpoint + HF upload
3. AMAP key verify
4. 3-sample sanity check
5. Full 100-sample eval (GAME + NW + LW + SWE-I)
6. Formal analysis report
7. Update results.tsv
