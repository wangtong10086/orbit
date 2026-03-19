# NAVWORLD Environment

## Key Facts
- Chinese travel planning agent evaluation (QQR)
- Uses Amap API (POI search, weather, directions) + mock transport data (flights/trains)
- Scoring: code 50 pts + LLM 50 pts = 100 total
- Standard OpenAI function calling format (tool_calls field)
- Everyone is weak (7-34 points), largest differentiation opportunity on leaderboard

## Scoring (from repos/affinetes/environments/qqr/scorer.py)

### Code Score (50 pts, locally testable)
- `50 * sqrt(IC_norm * Comp_norm) * tool_diversity_multiplier + fabrication_penalty`
- **IC (25 pts)**: 9 categories — flights, trains, POIs, prices, times, weather, distances, wind, travel_durations
- **Completeness (25 pts)**: plan sections present + grounded in tool data
- **Fabrication penalty**: up to -12.5 for citing data not from tools
- **Tool diversity**: [0.3, 1.1]x based on coverage

### LLM Score (50 pts, eval-time only)
- 5 dimensions x 10: practicality, analysis_depth, logic, user_experience, factual_grounding
- Scored by external LLM (gpt-oss-120b-TEE / Qwen3-235B)
- Cannot test locally — `TravelScorer(llm_validator=None)` skips this

### Hard Constraints (multiplicative, any fail = score crushed)
| Constraint | Fail Penalty | Trigger |
|-----------|-------------|---------|
| format_valid | 0.15x | output < 200 chars |
| tool_info_used | 0x-0.05x | IC below threshold (6-8 by type) |
| required_tools_called | 0.5x | <60% required tools |
| poi_names_verified | 0.7x | <2 POI names from tools |
| transport_grounded | 0.3x | fabricated flight/train numbers |

### 7 Problem Types
| Type | Must Call | Should Call | Nice to Have |
|------|----------|-------------|-------------|
| intercity | poi | — | direction |
| multiday | poi, weather | direction | around |
| hybrid | poi | direction | around |
| single_poi | poi, weather | around | direction |
| food_tour | poi, weather | direction | around |
| business | poi | — | direction |
| family_study | poi, weather | direction | around |

## Data Generation Pipeline

```
Problem gen (programmatic) → Tool calls (programmatic, real AMap API) → Plan gen (Claude Sonnet) → QQR score filter (>=25) → Ingest canonical
```

```bash
forge data navworld-gen -n 50 --model claude-sonnet-4-20250514 --type <type> -o data/navworld_claude_<type>.jsonl
forge data ingest <file> --env NAVWORLD --source claude_sonnet --no-upload
```

**Why Claude over qwen-max**: Claude avg 43 vs qwen-max avg 37 (code score). qwen-max frequently fabricates flight/train numbers and prices, triggering fabrication penalty + transport_grounded hard constraint.

## Current Data: 2394 entries (canonical)

| Source | Count | Avg Score | Notes |
|--------|-------|-----------|-------|
| qwen-max original 5 templates | ~2205 | 37/100 | intercity/multiday/hybrid/food_tour/business |
| D9 qwen-max | ~78 | mixed | single_poi + family_study |
| Claude Sonnet batch1 | 111 | 43/100 | 7 types, QQR >=35 |
| **batch2 generating** | ~230 | expected 40+ | 5 types |

## Format Requirements
1. Training: `tokenizer.apply_chat_template(messages, tools=tools)` — Qwen3 native `<tool_call>` format
2. Inference: sglang `--tool-call-parser qwen25`
3. Direction tool: must use coordinate `lng,lat` format
4. All entries: poi_search + weather + direction minimum

## Dead Ends (tried, failed)
- **D8 qwen-max diversity (8 Chinese types, 400 entries)**: ALL scored <25/100, entirely removed. qwen-max cannot generate quality Chinese diversity queries.
- **Haiku-based quality scoring**: Completely inconsistent with real QQR scorer (Haiku gave 7.5/50, QQR gave 37-43/100). Abandoned.
- **Plan rewriting (Haiku critique + Sonnet fix)**: Improved Haiku score 2.2→7.1 but real QQR score did not correspondingly improve. Generating new entries with Claude is 10x more effective than rewriting old ones.
- **Opus 4.6 vs Sonnet**: Identical code score (43.5 vs 43.5). Opus 5x more expensive with no additional benefit on code scoring.
