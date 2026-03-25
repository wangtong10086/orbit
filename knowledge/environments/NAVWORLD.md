# NAVWORLD Environment

## Key Facts
- Chinese travel planning agent evaluation (QQR scoring)
- Uses Amap API (POI search, weather, directions) + mock transport data (flights/trains)
- Scoring: code 50 pts + LLM 50 pts = 100 total
- **v2.21: NW 42.84** (current best), **v2.17a: 42.34** (previous best)
- v2.23 training with V6 data (2961 entries, per-step think, `--reasoning-parser qwen3`)

## Scoring (from repos/affinetes/environments/qqr/scorer.py)

### Code Score (50 pts, locally testable)
- `50 * sqrt(IC_norm * Comp_norm) * tool_diversity_multiplier + fabrication_penalty`
- **IC (25 pts)**: 9 categories — flights, trains, POIs, prices, times, weather, distances, wind, travel_durations
- **Completeness (25 pts)**: grounded plan sections checked via `_check_with_grounded_context`
- **Fabrication penalty**: up to -12.5 for citing data not from tools
- **Tool diversity**: tiered per type — must_call, should_call, nice_to_have. Floor 0.3x.

### Hard Constraints (multiplicative)
| Constraint | Fail Penalty | Trigger |
|-----------|-------------|---------|
| format_valid | 0.15x | output < 200 chars |
| tool_info_used | 0x/0.05x | IC < 6 (transport) / IC < 8 (other) |
| required_tools_called | 0.5x | <60% required tools |
| poi_names_verified | 0.7x | <2 POI names from tools |
| transport_grounded | 0.3x | fabricated flight/train numbers |
| tool_quality | 0.5x | <50% tool coverage or validity |

### LLM Score (50 pts, eval-time only)
- 5 dimensions × 10: practicality, logic, user_experience, analysis_depth, factual_grounding
- Code coupling: `llm *= min(1.0, code / (max_code * 0.6))` — low code caps LLM

## V6 Canonical — 2961 entries (2026-03-25)

| Type | Count | % |
|------|-------|---|
| intercity | 431 | 15% |
| business | 428 | 14% |
| hybrid | 428 | 14% |
| food_tour | 428 | 14% |
| single_poi | 424 | 14% |
| multiday | 424 | 14% |
| family_study | 398 | 13% |

- **Format**: Every assistant message has `<think>` block (tool_call steps + final plan)
- **Required for**: sglang `--reasoning-parser qwen3` (prevents tool_call misparse)
- **Quality**: QQR code score ≥45 for all new entries, min 35 overall
- **Validation**: 0 missing tool_call_id, 0 bad format, 100% audit pass
- **Source**: GPT-5.4 distillation via streaming
- **NW ratio**: ~19% of training mix (matches v2.17a's winning 19.7%)

### Data Format Example
```json
// Tool call step (每个都有 think)
{"role": "assistant",
 "content": "<think>\n用户需要从上海到杭州的交通方案，同时查询航班和火车进行对比。\n</think>\n",
 "tool_calls": [{"function": {"name": "search_flights", "arguments": "..."}}]}

// Tool result (必须有 tool_call_id)
{"role": "tool", "content": "[...]", "tool_call_id": "call_abc123"}

// Final plan (有 think 总结)
{"role": "assistant",
 "content": "<think>\n分析用户需求：...\n已完成工具调用：...\n</think>\n\n下面给你一份..."}
```

## Score History

| Version | Score | Key Change |
|---------|-------|-----------|
| v2.1-v2.8 | 1.5-12.6† | 早期迭代，format bugs，code-only eval |
| **v2.13b** | **25.13** | content=None 修复，+99% vs v2.7 |
| **v2.16** | **35.46** | GAME v12 think-then-act 数据 |
| **v2.17a** | **42.34** | NW 占比 19.7%，think 溢出最优 |
| v2.19 | 19.45 | ⚠️ Think 稀释：49% 无 think = 零分 |
| v2.20 | 37.77 | NW 占比降到 12.8%，被稀释 |
| **v2.21** | **42.84** | **CURRENT BEST.** NW 2966 + think + ratio 恢复 |
| v2.22 | 21.38 | ⚠️ `--reasoning-parser qwen3` + 旧数据冲突 |

†早期 code-only eval (max 50). v2.7+ includes CHUTES LLM scoring (max 100).

### v2.22 Regression Analysis
- 用旧 NW 数据（tool_call content 为空）+ `--reasoning-parser qwen3` 评测
- reasoning parser 把裸 `<tool_call>` 误解析，导致 tool calling 失败
- **已修复**: V6 数据每个 tool_call 都有 `<think>` 块，parser 正确分离 think 和 tool_call
- v2.23 使用 V6 数据训练中

### v2.21 Per-Type Analysis
| Type | Score | Issues |
|------|-------|--------|
| business | 51.6 | Best type |
| family_study | 48.1 | Good |
| single_poi | 46.4 | Good |
| hybrid | 44.6 | OK |
| multiday | 44.4 | OK |
| food_tour | 38.2 | Weak |
| **intercity** | **25.1** | **Worst — 9/15 < 25, low IC despite long plans** |

## Format Requirements (HARD RULES)
1. `tokenizer.apply_chat_template(messages, tools=tools)` — Qwen3 native format
2. Inference: sglang `--tool-call-parser qwen25` + `--reasoning-parser qwen3`
3. System prompt / tool schema must match eval's Chinese version exactly
4. Transport returns Chinese text strings, not JSON objects
5. **Every assistant message must have `<think>` block** (both tool_call and plan)
6. **Tool result messages must have `tool_call_id`** matching assistant's tool_call ID
7. **content must never be None** — use `""` for empty content
8. **`<tool_call>` must never appear in content** — use `tool_calls` field

## Data Generation Pipeline

```bash
# V6 pipeline (current) — streaming + per-step think + quality gate
forge data navworld-gen -n 50 --model gpt-5.4 --type <type> -o output.jsonl
# Quality audit
python3 scripts/navworld_quality_audit.py --threshold 45
```

Key files:
- `forge/data/navworld_gen.py` — generation + streaming + think + validation
- `forge/data/navworld_prompts.py` — system prompt, tool schema, user prompts (Chinese)
- `forge/data/navworld_plans.py` — tool call sequences per type
- `forge/data/amap_client.py` — AMap API client + mock transport
- `scripts/navworld_quality_audit.py` — QQR code scoring + quality analysis
- `scripts/navworld_add_think.py` — batch add think to existing data
- `scripts/navworld_add_step_think.py` — batch add per-step think

## Key Learnings
- **NW 占比 ~19.7% 最优** — 低了被稀释(v2.20)，数据量要跟着总量增长
- **Think 必须在每条 assistant 消息** — 否则 reasoning parser 和 think 稀释都会出问题
- **Code score 是瓶颈** — 低 code → LLM coupling 被压制。提高 IC 引用密度最有效
- **数据质量 > 数量** — 22 条弱 intercity（短 plan + 少对比）教坏模型
- **Streaming 必须** — 代理 504 超时，streaming 100% 成功率

## Dead Ends (DO NOT REPEAT)
- **content=None**: Qwen3 can't tokenize. Always `content=""`
- **Empty think `<think></think>`**: Model learns nothing. Add factual content
- **NW data without think**: GAME think gets diluted. NW must have own think
- **`<tool_call>` in content**: Breaks reasoning parser. Use `tool_calls` field
- **Missing tool_call_id**: Chat template can't match results. Must set in gen
- **Non-streaming API calls**: Proxy 504 on long gen. Must use streaming
- **qwen-max data**: All scored <25, removed
- **seq=16384**: Correlated with decline. Use 8192
- **Plan rewriting**: New generation 10x more effective
- **Eval without AMAP key**: v2.10/v2.11 scores invalid. Both keys needed on both machines
