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
- 5 dimensions × 10: practicality, analysis_depth, logic, user_experience, factual_grounding
- Scored by external LLM (gpt-oss-120b-TEE / Qwen3-235B)
- We cannot test locally — `TravelScorer(llm_validator=None)` skips this

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
问题生成(程序化) → 工具调用(程序化, 真实AMap API) → Plan生成(Claude Sonnet) → QQR评分过滤(≥25) → 入库
```

```bash
forge data navworld-gen -n 50 --model claude-sonnet-4-20250514 --type <type> -o data/navworld_claude_<type>.jsonl
forge data ingest <file> --env NAVWORLD --source claude_sonnet --no-upload
```

**为什么用 Claude 不用 qwen-max**: Claude avg 43 vs qwen-max avg 37 (code score)。qwen-max 频繁编造航班号和价格，触发 fabrication penalty + transport_grounded 硬约束。

## Current Data: 2394 entries (canonical)

| Source | Count | Avg Score | Notes |
|--------|-------|-----------|-------|
| qwen-max 原始5模板 | ~2205 | 37/100 | intercity/multiday/hybrid/food_tour/business |
| D9 qwen-max | ~78 | mixed | single_poi + family_study |
| Claude Sonnet batch1 | 111 | 43/100 | 7 types, QQR ≥35 |
| **batch2 生成中** | ~230 | expected 40+ | 5 types |

## Format Requirements
1. Training: `tokenizer.apply_chat_template(messages, tools=tools)` — Qwen3 native `<tool_call>` format
2. Inference: sglang `--tool-call-parser qwen25`
3. Direction tool: must use coordinate `lng,lat` format
4. All entries: poi_search + weather + direction minimum

## Dead Ends (tried, failed)
- **D8 qwen-max diversity (8 Chinese types, 400 entries)**: ALL scored <25/100, entirely removed. qwen-max 无法生成高质量中文 diversity 查询。
- **Haiku-based quality scoring**: 与真实 QQR scorer 完全不一致（Haiku 给 7.5/50，QQR 给 37-43/100），已废弃。
- **Plan 改写 (Haiku critique + Sonnet fix)**: 从 2.2 提到 7.1（Haiku 评分），但真实 QQR 分数没有对应提升。直接用 Claude 生成新条目更有效。
- **Opus 4.6 vs Sonnet**: code score 完全一样（43.5 vs 43.5），Opus 贵 5x 无额外收益。
