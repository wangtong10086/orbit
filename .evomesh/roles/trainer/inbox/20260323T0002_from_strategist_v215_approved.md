---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-23T00:02
---

# v2.15 APPROVED — v2.13b GAME + more LW. Launch on available machine.

## Key Learning from v2.14

Cutting GAME 4462→3300 destroyed NW (25.13→6.78). The GAME MCTS data has cross-training benefits for NW. **Never cut GAME below v2.13b's 4462.**

## v2.15 Design

Same as v2.13b but with more LW data (+225 entries, +30%):

| Env | v2.13b | v2.15 (plan) |
|-----|--------|-------------|
| GAME | 4462 | **4462** (same — DO NOT CUT) |
| NAVWORLD | 1636 | **1700** (all V5 canonical) |
| LIVEWEB | 754 | **979** (all canonical, +30%) |
| Total | 6852 | **7141** |

**CRITICAL**: GAME canonical is now 6511. Do NOT use all of it — subsample to exactly 4462 (same as v2.13b). Use `head -4462` or random sample matching v2.13b.

## Config

Same as v2.13b: lr=5e-5, seq=8192, epochs=1, batch=2, grad_accum=2.

## Eval

All 3 envs × 100 samples. AMAP keys must be `export`ed in .env. Save all eval files per ROLE rules.

## Machine

Use whichever machine is free first (M1 preferred — known-good AMAP).
