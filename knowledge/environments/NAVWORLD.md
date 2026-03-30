# NAVWORLD Environment

## Key Facts
- Chinese travel planning agent evaluation (QQR scoring)
- Uses Amap API (POI search, weather, directions) + mock transport data (flights/trains)
- Scoring: code 50 pts + LLM 50 pts = 100 total
- **v2.28 ckpt600: NW 44.08** (ALL-TIME BEST)
- Eval uses standard OpenAI Chat Completions API with tool calling

## Scoring

### Code Score (50 pts)
- `50 * sqrt(IC_norm * Comp_norm) * tool_diversity_multiplier + fabrication_penalty`
- **IC (25 pts)**: 9 categories — flights, trains, POIs, prices, times, weather, distances, wind, travel_durations
- **Completeness (25 pts)**: grounded plan sections (type-specific subscores)
- **IC proximity rule**: keyword+fact within 500 chars = full score, separated = 20%
- **LLM coupling**: `llm *= min(1.0, code / 30)` — code<30 severely caps LLM score

### Completeness Subscores (per type)
| Type | Subscores | Known Issue |
|------|-----------|-------------|
| single_poi | visit_plan, nearby, transport_info, tips, budget | **tips=0, budget=0** → Comp capped at ~16/25 |
| family_study | day_structure, child_friendly, education, dining, budget | **budget=0** → Comp ~20/25 |
| food_tour | restaurants, dishes, route, cost, tips | OK (~25/25) |
| business | — | OK (~25/25) |
| multiday | — | OK (~25/25) |

### Hard Constraints
| Constraint | Penalty | Trigger |
|-----------|---------|---------|
| format_valid | 0.15x | output < 200 chars |
| tool_info_used | 0x/0.05x | IC < 6 (transport) / IC < 8 (non-transport) |
| poi_names_verified | 0.7x | <2 POI names match |
| transport_grounded | 0.3x | fabricated transport IDs |

## Current Data: V9 (10782 canonical, generating more)

### Quality Profile (QQR code scores)
| Type | Count | Avg Code | Issue |
|------|-------|----------|-------|
| single_poi | 1052 | 41.2 | Comp low (tips/budget missing) — prompt fixed |
| family_study | 1551 | 46.3 | budget missing — prompt fixed |
| intercity | 1671 | 48.2 | OK |
| business | 1599 | 51.0 | Excellent |
| hybrid | 1588 | 51.1 | Excellent |
| food_tour | 1700 | 50.9 | Excellent |
| multiday | 1621 | 51.0 | Excellent |

### Format
- Standard OpenAI Chat Completions with multi-round tool calling
- `tools` field: eval-matching TOOLS_SCHEMA (6 tools)
- `tool_calls` + `tool_call_id` properly paired
- System prompt matches eval exactly

## Score History

| Version | Score | Key |
|---------|-------|-----|
| v2.13b | 25.13 | content=None fix |
| v2.17a | 42.34 | NW 19.7% ratio, best until v2.28 |
| v2.21 | 42.84 | Previous best |
| v2.25 | 40.57 | NW ratio 17.4%, LW dilution |
| **v2.28 ckpt200** | 37.41 | 4% training, NW recovered |
| **v2.28 ckpt600** | **44.08** | **ALL-TIME BEST**, 12% training |

### v2.28 ckpt600 Analysis
- 100 tasks, 0 errors, avg 44.08
- 26% tasks score ≤20 — model stops tool calling too early (avg 177s vs 280s for high-score)
- NW ratio: 10006/155109 = 6.5% (v2.17a was 19.7%)

## Data Generation

```bash
forge data navworld-gen -n 100 --model gpt-5.4 --type <type> -o output.jsonl
forge data ingest <file> --env NAVWORLD --source gpt5.4 --no-upload
```

Key files:
- `forge/data/navworld_gen.py` — generation pipeline (includes TOOLS_SCHEMA in output)
- `forge/data/navworld_prompts.py` — system prompt, tool schema, user prompts
- `forge/data/navworld_plans.py` — tool call sequences per type

## Key Learnings
- **IC proximity** — keyword+fact within 500 chars = full score
- **NW ratio matters** — 19.7% optimal, 6.5% still works but lower ceiling
- **Comp subscores** — single_poi needs explicit budget/tips in prompt
- **tools field required** — ms-swift needs it for proper tool_call tokenization
- **Multi-round tool calling** — standard OpenAI format, no merging needed
