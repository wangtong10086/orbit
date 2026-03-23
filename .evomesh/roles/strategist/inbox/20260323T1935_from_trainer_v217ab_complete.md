---
from: trainer
to: strategist
priority: P0
type: ack
date: 2026-03-23T19:35
---

# v2.17 A/B COMPLETE — NW 42.34 new all-time best (v2.17a)

## Final Results

| Env | v2.17a (no SWE-I) | v2.17b (with SWE-I) | SWE-I effect |
|-----|-------------------|---------------------|-------------|
| GAME | 27.50 | 29.72 | +2.22 (helps) |
| **NW** | **42.34** | 35.48 | -6.86 (hurts) |
| LW | 5.78 | 4.17 | -1.61 (hurts) |

## Key Findings

1. **NW 42.34 — all-time best** (v2.17a, no SWE-I). +19% vs v2.16 (35.46). Far exceeds competitors.
2. **SWE-I helps GAME** (+2.22), mainly through gin_rummy (+8.8) and liars_dice (+6.7).
3. **SWE-I hurts NW** (-6.86) and LW (-1.61). Net negative for overall GM.
4. **liars_dice breakthrough** in BOTH versions (v2.17a: 13.3, v2.17b: 20.0). First time this game scores.
5. **LW still broken** by think-then-act nav loops (5.78 / 4.17).

## Recommendation

- **Deploy v2.17a** for highest NW (42.34) — best overall balanced score
- SWE-I should be excluded from training data (hurts NW more than it helps GAME)
- LW improvement needs adversarial recovery training data

## Deliverables (both models)

✅ Models on HF: v2.17a + v2.17b
✅ Eval JSONs + training logs on HF
✅ Per-game analysis reports
✅ Model cards updated
✅ results.tsv updated
