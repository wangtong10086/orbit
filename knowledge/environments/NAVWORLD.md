# NAVWORLD Environment

## Key Facts
- Chinese travel planning agent evaluation (QQR)
- Uses Amap API (POI search, weather, directions) + mock transport data (flights/trains)
- Scoring: 50 points code scoring (info consistency + completeness) + 50 points LLM semantic scoring
- Standard OpenAI function calling format (tool_calls field)
- Everyone is weak (7-34 points), largest differentiation opportunity on leaderboard
- Requires AMAP_MAPS_API_KEY environment variable for eval

## Critical Format Issues (All Resolved)

### Issue 1: Text vs Tool Call Format
- Early synthetic data (navworld_sft.jsonl, 130 entries) used text format: `"Call tool: name({args})"`
- This is completely unusable — eval expects OpenAI `tool_calls` field
- **Fix**: Deleted navworld_sft.jsonl entirely, only use distill_all.jsonl with proper format

### Issue 2: apply_chat_template (v7→v8 breakthrough)
- v7 serialized tool_calls as `<tool_calls>JSON</tool_calls>` (custom text format)
- Qwen3 native format is `<tool_call>JSON</tool_call>` + `<tool_response>` + `<tools>`
- **Fix**: Use `tokenizer.apply_chat_template(messages, tools=tools)` to generate training text
- This ensures tool calling format is 100% aligned with Qwen3 tokenizer expectations

### Issue 3: sglang tool-call-parser (v8 breakthrough)
- Even with correct training data, sglang didn't parse `<tool_call>` text into OpenAI `tool_calls` field
- Eval environment sees `tool_calls=None` → score 0
- **Fix**: Add `--tool-call-parser qwen25` when starting sglang
- Both fixes together (apply_chat_template + tool-call-parser) broke NAVWORLD from 0% to 33% non-zero

### Issue 4: Missing Direction Tool Calls
- 59.7% of distill_all.jsonl samples missing the `direction` tool call
- Eval requires calling poi_search + weather + direction (all three)
- **Fix**: Filter to only keep samples containing all three tool types (~605 entries)
- v11: regenerated 2154 entries with 100% direction coverage

### Issue 5: Expired API Keys
- Old NAVWORLD data had expired Amap API keys → empty tool returns
- v9: 28 new entries supplemented with fresh API key
- v11: all entries regenerated with new API key

## Data Sources
- DynamoDB real data: score >= 0.3, ~248 entries (variable)
- Synthetic data: `forge/data/navworld_gen.py`, DashScope qwen3-max
- v11: 2154 entries total (biggest increase, +240% from v10's 632)

## Evaluation Results History
| Version | Samples | Mean | Non-zero | Notes |
|---------|---------|------|----------|-------|
| v5 | 100 | 0.000 | 0% | Text format data |
| v6 | — | 0.000 | 0% | Same issue |
| v7 | 18 | 0.000 | 0% | Custom serialization |
| v8 | 20 | 0.087 | 30% | apply_chat_template + tool-call-parser |
| v9 | 100 | 0.052 | 23% | More reliable (larger sample) |
| v10 | 100 | 0.051 | 28% | Flat vs v9 |
| v11 | 100 | 0.057 | 28% | +12% mean, 3.4x data increase |

## Current Best / Status
- v11: mean=0.057 (~5.7 leaderboard points), 28% non-zero
- v12: not evaluated on NAVWORLD (rental lost)
- Canonical data: 2248 entries with 100% direction coverage, fresh API keys
- Leaderboard top: wisercat 24.11, AnastasiaFantasy 22.16 (as of Block 7776423)

## SFT Plateau Root Cause (discovered by Data Agent 2026-03-18)
- Only **5 query templates** in 2248 entries, each ~448 copies with parameter variation
- Only 10 departure cities, ~25 destinations
- 1331 reused tool_call IDs across entries
- Plan length stdev=160 chars (extremely narrow)
- Only 2 markdown layout patterns
- **Conclusion**: model memorizes 5 recipes, not general tool-calling reasoning
- Fixing diversity (>20 query types) is higher priority than DPO

## Improvement Directions
- **Data diversity expansion** (root cause of plateau, not volume)
  - NAVWORLD diversity plan: `knowledge/environments/navworld_diversity_plan.md`
  - Phase 1: 8 new query types, 400 entries, ~$6.30
- Rejection sampling with eval scorer to filter low-quality entries
- DPO/GRPO after diversity is fixed (doing DPO on 5-template data would just reinforce templates)
- More diverse cities and scenarios
- Ensure all tool types are covered in every sample
- More diverse city/scenario coverage in synthetic data
