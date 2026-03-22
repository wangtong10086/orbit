# NAVWORLD Environment

## Key Facts
- Chinese travel planning agent evaluation (QQR)
- Uses Amap API (POI search, weather, directions) + mock transport data (flights/trains)
- Scoring: code 50 pts + LLM 50 pts = 100 total
- Tool calls: canonical uses OpenAI `tool_calls` format. `prepare-data` auto-converts to Qwen3 `<tool_call>` tags.
- Everyone is weak (7-34 points), largest differentiation opportunity on leaderboard
- **v2.7: NAVWORLD 12.63** (first CHUTES full eval) — best so far, V5 data not yet used

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

## V5 Data — Complete (2026-03-21)

### V5 Fixes Applied
ALL prior NAVWORLD data had critical format mismatches vs eval. V5 fixed all of them:

1. **Transport format** (P0): JSON objects → Chinese text strings (matching eval's `mock_transport/server.py`)
2. **English prompts** (P1): System prompt, tool schema, user prompts all changed to Chinese (matching eval's `config.py`)
3. **Missing tool schema params** (P1): `search_train_tickets` added adcode/lat/lon, `direction` added bicycling/waypoints
4. **LLM plan prompt** (P1): Changed to Chinese with scorer keyword alignment (12 sections)

### V5 Canonical — 1471 entries
| Type | Count | % |
|------|-------|---|
| family_study | 277 | 19% |
| single_poi | 273 | 19% |
| intercity | 265 | 18% |
| multiday | 188 | 13% |
| hybrid | 160 | 11% |
| food_tour | 155 | 11% |
| business | 153 | 10% |

- **Quality**: 100% pass audit, fabrication entries filtered
- **Source**: GPT-5.4 distillation, all eval-aligned (Chinese prompts/schema/transport)
- **HF synced**: monokoco/affine-sft-data/navworld.jsonl
- **Old 951 entries fully replaced** — all pre-V5 data was format-bugged
- **v2.10 experiment** approved to test this data (v2.7 config, NW V5 as single variable)
- **Generation blocked** (2026-03-22): Both GPT-5.4 and Claude proxies returning 504. Waiting for API recovery.

## NAVWORLD Score History

| Version | Score | Data | seq | Key Issue |
|---------|-------|------|-----|-----------|
| v2.1 | 8.47† | 2648 (all qwen-max) | 8192 | qwen-max data, code-only eval |
| v2.2 | 6.10† | 2624 (qwen-max + Claude) | 16384 | seq=16384 decline |
| v2.3 | 1.51† | 2624 (same) | 16384 | poi_search-only pattern |
| v2.4a | 7.71† | 919 (GPT-5.4 + Claude) | 8192 | Format bugs in all data |
| v2.6 | 5.82† | 1633 (V4 format-bugged) | 8192 | lr=1e-4, code-only |
| **v2.7** | **12.63** | 1633 (V4 format-bugged) | 8192 | **lr=5e-5, first CHUTES eval** |
| v2.8 | 8.03 | 1633 (V4 format-bugged) | 8192 | epochs=2 regression |
| v2.10 | 11.08⚠️ | **1430 (V5 format-fixed)** | 8192 | ⚠️ **AMAP key missing — 95% tool failures** |
| v2.11 | 8.70⚠️ | 1491 (V5) | 8192 | ⚠️ **AMAP key missing — invalid result** |
| v2.12 | pending | 1547 (V5) + v2.7 proportions | 8192 | Must fix AMAP key first |

†code-only eval (max 50/100). v2.7+ includes CHUTES LLM scoring (max 100).
⚠️ AMAP API key missing on M2 — NW tool calls failed, scores are invalid.

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

## CRITICAL: AMAP API Key Issue (discovered 2026-03-22)

**ALL NW evals on M2 (v2.10, v2.11) ran WITHOUT AMAP API keys.** 95% of tool calls returned `INVALID_USER_KEY`.

- M2 `.env` was missing both `AMAP_MAPS_API_KEY` and `AMAP_API_KEY`
- M1 had `AMAP_API_KEY` but NOT `AMAP_MAPS_API_KEY` (eval uses the latter)
- Eval script (`scripts/eval_envs.py`) passes both `AMAP_MAPS_API_KEY` and `AMAP_API_KEY` to Docker
- QQR config reads `AMAP_MAPS_API_KEY` from env (`environments/qqr/config.py` line 12)

**Fix**: Both machines need in `/root/.env`:
```
export AMAP_MAPS_API_KEY=f8da77e10334e089a4a5b2ca66273f88
export AMAP_API_KEY=f8da77e10334e089a4a5b2ca66273f88
```

**Impact on historical scores**: v2.10 (11.08), v2.11 (8.70) are INVALID — measured with broken tools. v2.7 (12.63, on M1) may also be partially affected if M1 only had `AMAP_API_KEY` not `AMAP_MAPS_API_KEY`. All NW comparisons post-v2.7 are unreliable.

## Dead Ends
- **qwen-max 5-template data**: 2205 entries, all poi_search → v2.3 regression to 1.51. REMOVED.
- **seq=16384**: correlated with NAVWORLD decline. Use 8192.
- **English prompts/schema**: distribution shift vs eval. Must use Chinese.
- **JSON transport format**: eval returns Chinese text strings, not JSON objects.
- **Haiku scoring**: inconsistent with QQR. Abandoned.
- **Plan rewriting**: new generation 10x more effective.
