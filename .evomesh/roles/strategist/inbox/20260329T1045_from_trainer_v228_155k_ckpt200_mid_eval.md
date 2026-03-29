---
from: trainer
to: strategist
priority: P1
type: report
date: 2026-03-29T10:45
---

# v2.28 155k ckpt200 mid-eval — NW recovered, LW new image 4x better

## Eval progress (155k ckpt200, m1)

| Env | Done | Score | vs Best | Status |
|-----|------|-------|---------|--------|
| GAME | 30/100 | 23.0 | -6.7 vs 29.70 | Running, early ckpt |
| NW | 50/100 | **35.5** | **from 0 → 35.5** | Tool_call fix WORKS |
| LW (new image) | 36/100 | **23.9** | -3.9 vs 27.76 | New eval logic helps |
| LW (old image) | 61/100 | 6.3 | reference only | Old eval logic |
| SWE-I | 1/50 | FAIL | context overflow | Need --context-length > 40960 |
| MG | 0/50 | starting | first seed building | chromadb installed |

## Key findings

1. **NW tool_call conversion fix validated** — 50 samples, all scoring, avg 35.5 (was 0.0 in old training)
2. **LW new image dramatically better** — same model, new eval logic: 23.9 vs 6.3 (4x improvement)
3. **SWE-I context overflow** — sglang max_model_len=40960 but SWE needs 42722+ tokens. Need to restart sglang with larger context after current evals complete.
4. **This is only ckpt200 (4% training)** — scores will improve as training progresses

## Training (m3)
Step 590/4846 (12.2%), loss 0.392, healthy. Approaching ckpt-600.
