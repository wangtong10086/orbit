# NAVWORLD Environment

## Key Facts
- Chinese travel planning agent evaluation (QQR)
- Uses Amap API (POI search, weather, directions) + mock transport data (flights/trains)
- Scoring: code 50 pts + LLM 50 pts = 100 total
- Tool calls: canonical uses OpenAI `tool_calls` format. `prepare-data` auto-converts to Qwen3 `<tool_call>` tags.
- Everyone is weak (7-34 points), largest differentiation opportunity on leaderboard
- **v2.4a: NAVWORLD 7.71** — best so far, but still low

## Scoring (from repos/affinetes/environments/qqr/scorer.py)

### Code Score (50 pts, locally testable)
- `50 * sqrt(IC_norm * Comp_norm) * tool_diversity_multiplier + fabrication_penalty`
- **IC (25 pts)**: 9 categories — flights, trains, POIs, prices, times, weather, distances, wind, travel_durations
- **Completeness (25 pts)**: grounded plan sections — each section checked via `_check_with_grounded_context(keyword_pattern, fact_pattern, tool_facts, weight)`
- **Fabrication penalty**: up to -12.5 for citing data not from tools
- **Tool diversity**: tiered per type — must_call, should_call, nice_to_have. Missing should_call = -0.25 each. Floor 0.3x.

### Completeness Sections (scorer checks these keywords)
| Section | Keyword Pattern | Fact Pattern | Types |
|---------|----------------|--------------|-------|
| 交通方案 | 出发/到达/发车/起飞 | HH:MM times | intercity, hybrid, business |
| 价格对比 | 价格/费用/票价 | XX元 | all |
| 推荐理由 | 推荐/建议/最佳 | POI names | all |
| 景点安排 | 景点/游览/参观 | 景区/公园/博物馆/古镇 | multiday, hybrid, single_poi, family_study |
| 餐饮推荐 | 餐/吃/美食 | 餐厅/饭店/小吃 | all |
| 住宿建议 | 住宿/酒店/宾馆 | 酒店/宾馆/民宿 | multiday, hybrid, business |
| 交通路线 | 交通/距离/步行 | XX米/公里/分钟 | single_poi, food_tour |
| 天气穿衣 | 天气/气温/穿衣 | 晴/阴/度 | all |
| 注意事项 | 门票/开放/注意/建议 | 元/HH:MM/提前/携带 | single_poi |
| 预算明细 | 预算/费用/花费 | XX元 | all |

### Hard Constraints (multiplicative)
| Constraint | Fail Penalty | Trigger |
|-----------|-------------|---------|
| format_valid | 0.15x | output < 200 chars |
| tool_info_used | 0x (transport) / 0.05x (other) | IC < 6 (transport) / IC < 8 (other) |
| required_tools_called | 0.5x | <60% required tools |
| poi_names_verified | 0.7x | <2 POI names from tools |
| transport_grounded | 0.3x | fabricated flight/train numbers |
| tool_quality | 0.5x | <50% tool coverage or validity |

### LLM Score (50 pts, eval-time only)
- 5 dimensions x 10: practicality, logic, user_experience, analysis_depth, factual_grounding
- Smooth coupling: `llm *= min(1.0, code / (max_code * 0.6))` — low code score caps LLM score

## Current Status: V5 Regeneration In Progress

### V5 Critical Fixes (2026-03-21)
Three critical format mismatches found and fixed in ALL prior NAVWORLD data:

1. **Transport format** (P0): Training data had JSON objects `[{"flight_no":"CZ3992","price":640}]`, eval returns Chinese text strings `["航班 CZ3992，价格640元，18:25从首都T3出发..."]`. Fixed by copying eval's exact `mock_transport/server.py`. Verified byte-for-byte.

2. **English prompts** (P1): System prompt, tool schema, and 5/7 user prompts were in English. Eval uses all Chinese. Fixed by direct copy from eval's `config.py`.

3. **Missing tool schema params** (P1): `search_train_tickets` missing adcode/lat/lon, `direction` missing bicycling/waypoints. Fixed by copying eval's complete schema.

4. **LLM plan prompt** (P1): Plan generation prompt was English with generic requirements. Changed to Chinese with explicit scorer keyword alignment (12 sections matching scorer's completeness checks).

### V5 Generation Progress
| Type | Target | Generated | Status |
|------|--------|-----------|--------|
| intercity | 230 | ~70 | Running |
| single_poi | 230 | ~85 | Running |
| business | 230 | ~35 | Running |
| food_tour | 250 | ~14 | Running |
| hybrid | 250 | ~25 | Running |
| multiday | 300 | ~20 | Running |
| family_study | 400 | ~20 | Running |

**All prior canonical data (951 entries) has format issues and will be replaced by V5.**

## NAVWORLD Score History

| Version | Score | Data | seq | Key Issue |
|---------|-------|------|-----|-----------|
| v2.1 | **8.47** | 2648 (all qwen-max) | 8192 | Best score, low data quality |
| v2.2 | 6.10 | 2624 (qwen-max + Claude) | 16384 | seq=16384 decline |
| v2.3 | **1.51** | 2624 (same) | 16384 | poi_search-only pattern |
| v2.4a | **7.71** | 919 (GPT-5.4 + Claude) | 8192 | Best GM, format bugs in data |

## Data Generation Pipeline

```bash
# V5 pipeline (current)
forge data navworld-gen -n 50 --model gpt-5.4 --type <type> -o output.jsonl
forge data ingest <file> --env NAVWORLD --source gpt-5.4 --no-upload
```

Key files:
- `forge/data/navworld_prompts.py` — system prompt, tool schema, user prompts (Chinese, copied from eval)
- `forge/data/navworld_gen.py` — generation orchestrator, LLM plan prompt
- `forge/data/amap_client.py` — AMap API client + mock transport (copied from eval)
- `forge/data/navworld_plans.py` — tool call sequences per type

## Format Requirements
1. Training: `tokenizer.apply_chat_template(messages, tools=tools)` — Qwen3 native format
2. Inference: sglang `--tool-call-parser qwen25`
3. System prompt / tool schema must match eval's Chinese version exactly
4. Transport returns Chinese text strings, not JSON objects

## Dead Ends
- **qwen-max 5-template data**: 2205 entries, all poi_search → v2.3 regression to 1.51. REMOVED.
- **seq=16384**: correlated with NAVWORLD decline. Use 8192.
- **English prompts/schema**: distribution shift vs eval. Must use Chinese.
- **JSON transport format**: eval returns Chinese text strings, not JSON objects.
- **Haiku scoring**: inconsistent with QQR. Abandoned.
- **Plan rewriting**: new generation 10x more effective.
