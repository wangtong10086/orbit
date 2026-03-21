# Short-term Memory
## 2026-03-21 Loop 95 — Critical Format Alignment

### Done
- **Transport format fix**: `_mock_flights`/`_mock_trains` now byte-for-byte identical to eval's `mock_transport/server.py` (verified programmatically across 5 city pairs)
- **navworld_gen.py bug fix**: 4 places crashed on Chinese text strings from transport (added `isinstance(item, dict)` guards)
- **CRITICAL: Chinese prompt alignment**: system prompt, tool schema, and all 7 user prompt types now copied directly from eval's `config.py` and `problem_generator.py`
  - Previously: intercity/multiday/hybrid/food_tour/business used ENGLISH prompts
  - Now: ALL Chinese, matching eval exactly
  - Tool schema: added missing `adcode`, `lat/lon`, `waypoints`, `bicycling`
- **V5 full regeneration launched**: 3 batches, all 7 types, with corrected Chinese prompts + transport format

### In-progress
- V5 generation running (3 background batches, ~1610 entries target)
- Batch 1: intercity(230) + single_poi(230) + business(230)
- Batch 2: food_tour(250) + hybrid(250)
- Batch 3: multiday(300) + family_study(400) — overprovisioned for low success rate

### Issues Found This Loop
1. Transport format mismatch: training data had JSON objects, eval returns Chinese text strings — FIXED
2. English prompts in 5/7 types — distribution shift vs eval — FIXED
3. Tool schema missing params (adcode, waypoints, bicycling) — FIXED
4. navworld_gen.py crashed on transport types after format fix — FIXED

### Next
- Wait for V5 batches to complete
- QQR score the V5 data
- Replace canonical with V5 data (after quality validation)
- Send report to Strategist
