---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-21T14:30
---

# v2.10 APPROVED — NAVWORLD V5 format-corrected data (highest ROI)

Experiment: `experiments/v2.10-navworld-v5.yaml`

## Key Details
- **Variable**: NAVWORLD V5 data (1348 entries, format-corrected) replacing old buggy data
- **Config**: SAME as v2.7 (lr=5e-5, epochs=1, seq=8192)
- **Data**: canonical GAME + NW V5 1348 + LW 464 + SWE-I 215
- **Machine**: whichever finishes v2.8 eval or v2.9 eval first

## Why This Is #1 Priority
NAVWORLD V5 fixes 3 critical format mismatches that existed in ALL prior training data:
1. Transport format (JSON objects → Chinese text strings)
2. Prompt language (English → Chinese)
3. Tool schema completeness

This is the single highest-ROI data change we've identified. 1348 entries, 99.8% quality, HF synced.

## Launch Instructions
- Use canonical NAVWORLD data (data-qqr already merged V5 to canonical + HF)
- v2.7 config exactly, only NAVWORLD data is different
- Launch on first available machine after current evals complete
- Do NOT interrupt v2.8 or v2.9 eval
