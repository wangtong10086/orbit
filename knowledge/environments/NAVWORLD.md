# NAVWORLD Environment

## Key Facts
- Chinese travel planning agent evaluation (QQR)
- Uses Amap API (POI search, weather, directions) + mock transport data (flights/trains)
- Scoring: 50 points code scoring (IC + completeness geometric mean) + 50 points LLM semantic scoring = 100 total
- Standard OpenAI function calling format (tool_calls field)
- Everyone is weak (7-34 points), largest differentiation opportunity on leaderboard
- Requires AMAP_MAPS_API_KEY environment variable for eval

## Scoring Breakdown (from repos/affinetes/environments/qqr/scorer.py)

### Code Score (50 pts max)
- `50 * sqrt(IC_norm * Comp_norm) * tool_diversity_multiplier + fabrication_penalty`
- **Info Consistency (IC, 25 pts)**: tool data cited in plan (flights, trains, POIs, prices, weather, distances, etc.)
- **Completeness (25 pts)**: required plan sections present, grounded in tool data
- **Fabrication penalty**: up to -12.5 pts for citing data not from tools
- **Tool diversity multiplier**: [0.3, 1.1]x based on tool coverage

### LLM Score (50 pts max)
- 5 dimensions × 10 pts: practicality, analysis_depth, logic, user_experience, factual_grounding
- Scored by external LLM at eval time (cannot test locally)

### Hard Constraints (multiplicative gates)
- `format_valid`: output >= 200 chars (0.15x if fail)
- `tool_info_used`: IC >= 6-8 depending on type (0x-0.05x if fail)
- `required_tools_called`: >= 60% required tools (0.5x if fail)
- `poi_names_verified`: >= 2 POI names from tools (0.7x if fail)
- `transport_grounded`: transport IDs from tools (0.3x if fail)

### 7 Problem Types (eval)
| Type | Required Tools | Tool Tiers |
|------|---------------|------------|
| intercity | poi, direction, weather, flights, trains | must: poi |
| multiday | poi, around, direction, weather | must: poi+weather, should: direction |
| hybrid | poi, around, direction, weather, flights, trains | must: poi, should: direction |
| single_poi | poi, around, direction, weather | must: poi+weather, should: around |
| food_tour | poi, around, direction, weather | must: poi+weather, should: direction |
| business | poi, direction, weather, flights, trains | must: poi |
| family_study | poi, around, direction, weather | must: poi+weather, should: direction |

## Current Data Status

**Canonical**: `data/canonical/navworld.jsonl` — **2394 entries** (cleaned 2026-03-19)

| Source | Count | QQR Score | Notes |
|--------|-------|-----------|-------|
| Original qwen-max (5 templates) | ~2205 | avg 37/100 | 5 query types, EN prompts |
| D8 Phase 1 diversity (qwen-max) | **0** (removed) | <25/100 | ALL 400 entries removed — scored too low |
| D9 qwen-max (single_poi+family_study) | ~78 | varied | 22 low-score removed |
| D10 Claude Sonnet | 111 | avg 40-44/100 | 7 types, highest quality |

### Key Findings
- **Claude Sonnet vs qwen-max**: Claude avg 43.5 vs qwen-max avg 37 (code score)
- **D8 diversity entries were ALL garbage**: 0/400 scored >=25 — qwen-max cannot generate quality Chinese diversity queries
- **single_poi type scores low by design**: no transport data → IC categories empty → lower ceiling
- Real QQR scorer available locally for quality gating

## Data Generation Pipeline

```bash
# Generate with Claude (best quality)
forge data navworld-gen -n 50 --model claude-sonnet-4-20250514 --type <type> -o data/navworld_claude_<type>.jsonl

# Generate with qwen-max (cheaper, lower quality)
forge data navworld-gen -n 50 --type <type> -o data/navworld_qwen_<type>.jsonl

# Score with real QQR scorer (repos/affinetes/environments/qqr/scorer.py)
# Filter >= 25, ingest to canonical
forge data ingest <file> --env NAVWORLD --source <source>
```

## Critical Format Issues (All Resolved)

1. **apply_chat_template**: Must use `tokenizer.apply_chat_template(messages, tools=tools)` for Qwen3 native format
2. **sglang tool-call-parser**: Must use `--tool-call-parser qwen25` at inference
3. **Direction tool**: Must use coordinate format (lng,lat), 99%+ coverage achieved
4. **All tool types covered**: Every entry calls poi_search + weather + direction minimum

## Dead Ends
- **D8 Phase 1 diversity (qwen-max)**: 400 entries, ALL scored <25/100. qwen-max can't do quality Chinese diversity queries.
- **Haiku-based scoring**: Gave 7.5/50 avg, completely inconsistent with real QQR scorer (37-43/100). Abandoned.
- **Plan rewriting (Haiku critique + Sonnet fix)**: ROI too low. Direct Claude generation is 10x more effective.
