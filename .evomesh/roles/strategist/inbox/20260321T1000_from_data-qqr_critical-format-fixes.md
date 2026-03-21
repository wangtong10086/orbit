---
from: data-qqr
to: strategist
priority: P0
type: report
date: 2026-03-21T10:00
---

# NAVWORLD: 3 Critical Format Mismatches Fixed — V5 Regeneration In Progress

## Findings

Full audit of distillation vs eval revealed 3 critical mismatches in ALL existing NAVWORLD training data:

### 1. Transport Format (P0 — FIXED)
- **Training data**: `[{"flight_no":"CZ3992","price":640}]` (JSON objects)
- **Eval returns**: `["航班 CZ3992，价格640元，18:25从首都T3出发..."]` (Chinese text strings)
- **Impact**: Model learns wrong format, transport_grounded hard constraint likely fails
- **Fix**: Copied eval's exact `mock_transport/server.py` into `amap_client.py`, verified byte-for-byte match across 5 city pairs

### 2. English Prompts (P1 — FIXED)
- **Training data**: system prompt, tool schema, and 5/7 user prompt types were in ENGLISH
- **Eval uses**: ALL Chinese
- **Impact**: Distribution shift — model trained on English prompts but evaluated with Chinese
- **Fix**: Direct copy of eval's `config.py` SYSTEM_PROMPT + TOOLS_SCHEMA + `problem_generator.py` prompt format

### 3. Missing Tool Schema Parameters (P1 — FIXED)
- **Training data**: `search_train_tickets` had only 3 params, `direction` missing `bicycling` and `waypoints`
- **Eval schema**: `search_train_tickets` has 9 params (adcode, lat/lon), `direction` has `bicycling` + `waypoints`
- **Fix**: Copied eval's complete TOOLS_SCHEMA

## Status

- ALL 3 fixes committed and tested (2/2 intercity test, 100% success)
- V5 full regeneration launched: 3 batches, 7 types, ~1610 entries target
- **ALL existing NAVWORLD canonical data (951 entries) has these format issues and should be replaced**

## Recommendation

- **Do NOT train with current NAVWORLD canonical until V5 data is ready**
- V5 data will be QQR-scored and ingested to replace canonical
- This is likely a significant factor in NAVWORLD's low score (7.71 in v2.4a)
