# NAVWORLD Environment

## Key Facts
- Chinese travel planning agent evaluation (QQR)
- Uses Amap API (POI search, weather, directions) + mock transport data (flights/trains)
- Scoring: code 50 pts + LLM 50 pts = 100 total
- Tool calls: canonical uses OpenAI `tool_calls` format. `prepare-data` auto-converts to Qwen3 `<tool_call>` tags.
- Everyone is weak (7-34 points), largest differentiation opportunity on leaderboard
- **v2.3: NAVWORLD 1.51** — severe regression from v2.1 (8.47) due to qwen-max template pollution

## Scoring (from repos/affinetes/environments/qqr/scorer.py)

### Code Score (50 pts, locally testable)
- `50 * sqrt(IC_norm * Comp_norm) * tool_diversity_multiplier + fabrication_penalty`
- **IC (25 pts)**: 9 categories — flights, trains, POIs, prices, times, weather, distances, wind, travel_durations
- **Completeness (25 pts)**: plan sections present + grounded in tool data
- **Fabrication penalty**: up to -12.5 for citing data not from tools
- **Tool diversity**: [0.3, 1.1]x based on coverage

### LLM Score (50 pts, eval-time only)
- 5 dimensions x 10: practicality, analysis_depth, logic, user_experience, factual_grounding
- Cannot test locally

### Hard Constraints (multiplicative)
| Constraint | Fail Penalty | Trigger |
|-----------|-------------|---------|
| format_valid | 0.15x | output < 200 chars |
| tool_info_used | 0x-0.05x | IC below threshold |
| required_tools_called | 0.5x | <60% required tools |
| poi_names_verified | 0.7x | <2 POI names from tools |
| transport_grounded | 0.3x | fabricated flight/train numbers |

## Current Data: 919 entries (canonical, post-cleanup)

| Source | Count | Avg Code Score | Notes |
|--------|-------|----------------|-------|
| GPT-5.4 V2 | ~500 | 40+/50 | V2 pipeline, diverse tools, direction format fixed |
| Claude Sonnet | 341 | 39.4/50 | all 7 types, QQR ≥25 |
| qwen3-max labeled | 78 | ~38/50 | has problem_type, kept provisionally |
| **Total** | **919** | ~39.5/50 | **qwen-max 5-template data (2205) REMOVED** |

### Tool Diversity (critical metric)
- Avg tools per entry: **5.4**
- 100% entries use ≥3 tools
- 77% entries use ≥5 tools (poi_search + weather + direction + flights + trains + around_search)
- **Zero entries with only poi_search** — the qwen-max template problem is eliminated

### Type Distribution (all 7 types balanced)
| Type | Count | % |
|------|-------|---|
| intercity | 230 | 25% |
| business | 177 | 19% |
| single_poi | 128 | 14% |
| food_tour | 100 | 11% |
| hybrid | 95 | 10% |
| multiday | 80 | 9% |
| family_study | 73 | 8% |

## NAVWORLD Regression Analysis

| Version | Score | Data | seq | Nonzero | Key Issue |
|---------|-------|------|-----|---------|-----------|
| v2.1 | **8.47** | 2648 (all qwen-max) | 8192 | ~40% | Best score, but data quality low |
| v2.2 | 6.10 | 2624 (qwen-max + Claude) | 16384 | 37% | seq=16384 started decline |
| v2.3 | **1.51** | 2624 (same) | 16384 | 9% | Model only calls poi_search |

**Root cause**: 84% qwen-max data (5 templates, all poi_search-heavy) + seq=16384
**Fix in v2.4**: removed qwen-max, seq=8192, 919 clean entries with diverse tool usage

## Data Generation Pipeline

```bash
# GPT-5.4 (current default)
forge data navworld-gen -n 50 --model gpt-5.4 --type <type> -o output.jsonl
# Ingest (after QQR quality gate ≥25)
forge data ingest <file> --env NAVWORLD --source gpt-5.4 --no-upload
```

V2 pipeline fix: direction returns formatted 米/公里/分钟 (not raw meters/seconds).

## Format Requirements
1. Training: `tokenizer.apply_chat_template(messages, tools=tools)` — Qwen3 native format
2. Inference: sglang `--tool-call-parser qwen25`
3. Both required — without either, NAVWORLD scores 0

## Dead Ends
- **qwen-max 5-template data**: 2205 entries, all poi_search pattern → caused v2.3 regression to 1.51. REMOVED.
- **seq=16384**: correlated with NAVWORLD decline. Reverted to 8192 for v2.4.
- **D8 qwen-max diversity**: 400 entries, ALL scored <25/100. Removed.
- **Haiku scoring**: inconsistent with QQR. Abandoned.
- **Plan rewriting**: doesn't improve real scores. New generation 10x more effective.
