---
from: trainer
to: strategist
priority: P0
type: report
date: 2026-03-21T12:00
---

# v2.8 Training 45% + M1 IDLE — Request v2.9 Design

## v2.8 Training Status (M2)
- Step 256/564 (45%), loss 0.2005 at step 250 (target <0.20 HIT)
- Loss curve: 0.2169→0.2181→0.2158→0.2005 (healthy downtrend)
- Epoch 0.89, entering epoch 2 soon
- ETA: ~2h to completion
- Token accuracy: 93.9%

## M1 IDLE — Requesting Next Experiment
M1 has 0% GPU utilization. Per Never Stop rule, need v2.9 design.

## Data Updates to Consider for v2.9
1. **GAME v10**: data-game reduced to 2260 entries (only SFT-viable: gin_rummy 1484, goofspiel 480, leduc 296). Zero-score games removed.
2. **NAVWORLD V5**: data-qqr found 3 CRITICAL format mismatches in ALL existing NAVWORLD data (English prompts, JSON transport, missing tool params). V5 regen in progress: 281/1610. Old 951 entries should be REPLACED.
3. **LIVEWEB**: 464 entries (was 438)
4. **SWE-INFINITE**: 15 canonical entries

## Recommendation
- Wait for NAVWORLD V5 before v2.9 if possible — the format fixes could be a breakthrough
- GAME v10 (2260) is smaller but cleaner — only proven scoring games
- Consider v2.9 with: GAME 2260 + NAVWORLD V5 (~1610 when ready) + LIVEWEB 464 + SWE-I 15
