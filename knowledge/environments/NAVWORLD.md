# NAVWORLD Environment

## Key Facts
- Chinese travel planning agent evaluation (QQR)
- Uses Amap API (POI search, weather, directions) + mock transport data (flights/trains)
- Scoring: code 50 pts + LLM 50 pts = 100 total
- Tool calls embedded as `<tool_call>` tags in assistant content (NOT OpenAI tool_calls field)
- Everyone is weak (7-34 points), largest differentiation opportunity on leaderboard
- v2.2 eval: NAVWORLD 6.10 (regression from v2.1's 8.47)

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

**Why Claude over qwen-max**: Claude avg 39.7/50 vs qwen-max avg 38.1/50 (code score). qwen-max has 4% fabrication + transport_grounded failures.

## Current Data: 2624 entries (canonical)

| Source | Count | Avg Code Score | Notes |
|--------|-------|----------------|-------|
| qwen-max (5 templates) | 2205 | 38.1/50 | no problem_type field, intercity-heavy |
| Claude Sonnet (batch1+2) | 419 | 39.7/50 | all 7 types, QQR >=25 |
| **Total** | **2624** | ~38.4/50 | |

### Per-Type Quality (Claude entries, local QQR code scorer)
| Type | Count | Avg Code | Min | Max | Status |
|------|-------|----------|-----|-----|--------|
| intercity | 70 | 43.1 | 38.1 | 45.8 | strongest |
| business | 70 | 42.6 | 35.4 | 45.6 | strong |
| hybrid | 69 | 42.3 | 31.3 | 48.6 | strong |
| multiday | 70 | 40.0 | 32.5 | 44.4 | good |
| family_study | 68 | 37.2 | 25.8 | 39.3 | medium |
| food_tour | 43 | 36.4 | 30.8 | 40.7 | **undercount** |
| single_poi | 29 | 28.4 | 25.5 | 28.8 | **weakest** |

### Old Data Type Distribution (inferred, 2205 entries)
| Type | Count | % |
|------|-------|---|
| intercity | 729 | 33% |
| food_tour | 635 | 29% |
| business | 445 | 20% |
| multiday | 208 | 9% |
| family_study | 140 | 6% |
| single_poi | 48 | 2% |

### Data Gaps (priority order)
1. **single_poi**: only 29 Claude entries, avg 28.4 — need +40 entries, target avg 35+
2. **food_tour**: only 43 Claude entries — need +27 to reach 70
3. **Old data lacks problem_type**: 2205 entries without type labels

## Format Requirements
1. Training: `tokenizer.apply_chat_template(messages, tools=tools)` — Qwen3 native `<tool_call>` format
2. Inference: sglang `--tool-call-parser qwen25`
3. Direction tool: must use coordinate `lng,lat` format
4. All entries: poi_search + weather + direction minimum

## Scoring Insights (2026-03-20 deep analysis)
- **tool_quality HC fails on ALL entries** (both old and Claude): 0.5x multiplier, not fatal but caps code score ~45
- **IC 9/9 coverage**: 77.6% of entries, 18.7% at 8/9 (local-only types without flights)
- **Fabrication rate**: 1.8% entries, mostly in old qwen-max data
- **Completeness is type-specific**: each type has different subscore checks (day_structure, transport, dining, etc.)
- **Geometric mean (IC×Comp)**: Comp=0 kills score entirely — single_poi weak because comp subscores (visit_plan, nearby, transport_info, tips, budget) are harder to satisfy
- **All plans > 200 chars**: zero format_valid failures
- **Local scoring caveat**: scorer `_get_result_string()` uses `str()` on Python objects → single quotes; eval-time uses JSON strings → double quotes. POI extraction differs between local and eval.

## Dead Ends (tried, failed)
- **D8 qwen-max diversity (8 Chinese types, 400 entries)**: ALL scored <25/100, entirely removed. qwen-max cannot generate quality Chinese diversity queries.
- **Haiku-based quality scoring**: Completely inconsistent with real QQR scorer (Haiku gave 7.5/50, QQR gave 37-43/100). Abandoned.
- **Plan rewriting (Haiku critique + Sonnet fix)**: Improved Haiku score 2.2→7.1 but real QQR score did not correspondingly improve. Generating new entries with Claude is 10x more effective than rewriting old ones.
- **Opus 4.6 vs Sonnet**: Identical code score (43.5 vs 43.5). Opus 5x more expensive with no additional benefit on code scoring.
