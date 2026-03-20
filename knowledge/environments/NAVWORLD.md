# NAVWORLD Environment

## Key Facts
- Chinese travel planning agent evaluation (QQR)
- Uses Amap API (POI search, weather, directions) + mock transport data (flights/trains)
- Scoring: code 50 pts + LLM 50 pts = 100 total
- Tool calls: canonical uses `<tool_call>` tags in content. `forge data ingest` auto-normalizes from OpenAI `tool_calls` format.
- Everyone is weak (7-34 points), largest differentiation opportunity on leaderboard
- v2.2 eval: NAVWORLD 6.10 (regression from v2.1's 8.47). v2.3 training in progress.

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
Problem gen (programmatic) → Tool calls (programmatic, real AMap API) → Plan gen (LLM) → QQR score filter (>=25) → Ingest canonical
```

```bash
# GPT-5.4 (current default — available via OpenAI-compatible API)
forge data navworld-gen -n 50 --model gpt-5.4 --type <type> -o data/navworld_gpt54_<type>.jsonl
# Claude Sonnet (if Anthropic API key available)
forge data navworld-gen -n 50 --model claude-sonnet-4-20250514 --type <type> -o data/navworld_claude_<type>.jsonl
# Ingest to canonical (after QQR quality gate)
forge data ingest <file> --env NAVWORLD --source <model> --no-upload
```

**Model comparison** (code score, /50): GPT-5.4 V2 avg 40+, Claude Sonnet 39.4, qwen-max 38.1.
V2 pipeline critical fix: direction format (meters→米/公里) unlocks transport_info comp score.

## Current Data: 2725 entries (canonical)

| Source | Count | Avg Code Score | Notes |
|--------|-------|----------------|-------|
| qwen-max (5 templates) | 2205 | 38.1/50 | no problem_type field, intercity-heavy |
| Claude Sonnet (batch1+2) | 419 | 39.4/50 | all 7 types, QQR >=25 |
| GPT-5.4 V2 | 101 | 40+/50 | all 7 types, V2 pipeline, all ≥25 |
| **Total** | **2725** | ~38.6/50 | |

### Type Coverage (Claude + GPT-5.4, 520 labeled entries)
| Type | Count | Status |
|------|-------|--------|
| single_poi | 82 | balanced |
| intercity | 80 | balanced |
| business | 77 | balanced |
| food_tour | 71 | balanced |
| hybrid | 71 | balanced |
| multiday | 71 | balanced |
| family_study | 68 | balanced |

### Old Data Type Distribution (inferred, 2205 entries)
| Type | Count | % |
|------|-------|---|
| intercity | 729 | 33% |
| food_tour | 635 | 29% |
| business | 445 | 20% |
| multiday | 208 | 9% |
| family_study | 140 | 6% |
| single_poi | 48 | 2% |

### Remaining Gaps
1. **Old data lacks problem_type**: 2205 entries without type labels (training still works, just can't weight by type)
2. **Comp ceilings**: tips/budget/cost score 0 for all entries — tool data lacks price info, not fixable by prompt

## Format Requirements
1. Training: `tokenizer.apply_chat_template(messages, tools=tools)` — Qwen3 native `<tool_call>` format
2. Inference: sglang `--tool-call-parser qwen25`
3. Direction tool: must use coordinate `lng,lat` format
4. All entries: poi_search + weather + direction minimum

## Scoring Insights (2026-03-20 deep analysis)
- **IC 9/9 coverage**: 77.6% of entries, 18.7% at 8/9 (local-only types without flights)
- **Fabrication rate**: 1.8% entries, mostly in old qwen-max data
- **Completeness is type-specific**: each type has different subscore checks (day_structure, transport, dining, etc.)
- **Geometric mean (IC×Comp)**: Comp=0 kills score entirely — single_poi weak because comp subscores are harder to satisfy
- **All plans > 200 chars**: zero format_valid failures
- **Local scoring limitation**: tool_quality HC and some fact extraction may differ from eval-time due to tool trace format differences. Use local scores for relative comparison only.

## Dead Ends (tried, failed)
- **D8 qwen-max diversity (8 Chinese types, 400 entries)**: ALL scored <25/100, entirely removed. qwen-max cannot generate quality Chinese diversity queries.
- **Haiku-based quality scoring**: Completely inconsistent with real QQR scorer (Haiku gave 7.5/50, QQR gave 37-43/100). Abandoned.
- **Plan rewriting (Haiku critique + Sonnet fix)**: Improved Haiku score 2.2→7.1 but real QQR score did not correspondingly improve. Generating new entries with Claude is 10x more effective than rewriting old ones.
- **Opus 4.6 vs Sonnet**: Identical code score (43.5 vs 43.5). Opus 5x more expensive with no additional benefit on code scoring.
