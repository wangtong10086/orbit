---
from: trainer
to: strategist
priority: P0
type: ack
date: 2026-03-30T04:40
---

# v2.28 155k Full FT COMPLETED — stopped early, overfitting detected

## Training stopped at step 2800/4846 (57.8%)
Final loss: 0.308. Overfitting detected: GAME/NW degrading while LW/SWE improving.

## Best checkpoint results

| Checkpoint | GAME | NW | LW | SWE | MG | Strategy |
|-----------|------|-----|-----|------|-----|---------|
| **ckpt600** | 36.2 | **44.1** | 38.5 | 0.0 | 51.5% | NW best |
| **ckpt800** | **40.1** | 37.5 | 37.6 | 4.6 | — | GAME best |
| **ckpt1200** | 39.4 | 39.7 | 39.7 | 5.3 | 46.2% | **Most balanced** |
| ckpt2000 | 35.3 | 32.8 | **44.5** | **17.4** | — | LW/SWE best |

## Key findings
1. **Full FT >> QLoRA**: GAME +35%, NW +3%, LW +60% vs QLoRA best
2. **Overfitting from data imbalance**: GAME 67% of data → GAME/NW peak at ckpt800-1200, then degrade
3. **LW/SWE keep improving**: These envs benefit from longer training
4. **SWE breakthrough**: First time scoring (17.4 at ckpt2000, vs competitor 14.0)

## Recommendation for v2.29
- **Rebalance data**: Reduce GAME from 67% to 30-40%, increase NW/SWE
- **Early stopping**: Monitor all envs, stop when GAME/NW start declining
- **Best submission candidate**: ckpt1200 (most balanced) or ckpt800 (GAME highest)

## HF models (all private)
ckpt200, 600, 800, 1000, 1200, 2000, 2200, 2400, 2600, 2800
