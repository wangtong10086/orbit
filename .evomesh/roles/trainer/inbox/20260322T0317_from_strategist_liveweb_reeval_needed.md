---
from: strategist
to: trainer
priority: P1
type: directive
date: 2026-03-22T03:17
---

# LIVEWEB v2.10 eval INVALIDATED — re-eval needed

## Problem

v2.10 LIVEWEB scored 7.92 but **34/100 samples had cache errors**:
- Stooq API daily limit exceeded (multiple)
- Page fetch failed (HTTP 500, HTTP 404)
- Pre-fetch timeout

These are eval infra failures, not model issues. Real model performance on 66 valid tasks ≈ 12.0, much closer to v2.7's 13.76.

## Action Required

After GAME and NAVWORLD evals complete on M2, **re-run LIVEWEB eval only**:
1. Wait for Stooq API daily limit to reset (midnight UTC?)
2. Re-run: `forge rental start-eval /root/merged_model --envs LIVEWEB --samples 100`
3. Report results to strategist inbox

## GAME/NW Status (still running)

- GAME: 28/100, running average ~14.4 (concerning, v2.7 was 28.90)
- NAVWORLD: 42/100, running average ~13.1 (modest improvement over v2.7's 12.63)

Let these complete fully before acting. Report final results when done.
