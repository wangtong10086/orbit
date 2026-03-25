# NAVWORLD Environment

## Key Facts
- Chinese travel planning agent evaluation (QQR scoring)
- Uses Amap API (POI search, weather, directions) + mock transport data (flights/trains)
- Scoring: code 50 pts + LLM 50 pts = 100 total
- **v2.21: NW 42.84** (current best)
- **v2.23: NW 34.88** (LW 稀释, no reasoning-parser → best config)
- V7 data ready: 3865 entries, IC-optimized plan format

## Scoring — IC Proximity Rule (CRITICAL)

### 3-Tier Scoring (`_check_with_grounded_context`)
| Tier | Condition | Score |
|------|-----------|-------|
| **Tier 1 (Full)** | keyword + context + tool_fact **同一段落** | 100% |
| **Tier 2 (Half)** | keyword + tool_fact **500 字符内** | 50% |
| **Tier 2 (Weak)** | keyword + tool_fact **>500 字符** | 20% |
| **Fail** | 无 tool_fact | 0% |

**核心优化点**：plan 中每提到一个主题时，必须在同一段落内紧跟引用工具数据。分开写会被降到 20-50%。

### Code Score (50 pts)
- `50 * sqrt(IC_norm * Comp_norm) * tool_diversity_multiplier + fabrication_penalty`
- **IC (25 pts)**: 9 categories — flights, trains, POIs, prices, times, weather, distances, wind, travel_durations
- **Completeness (25 pts)**: grounded plan sections
- **IC divisor = 0.5**: 需要 50%+ 的工具数据被引用才能满分
- **Breadth penalty**: 如果 4+ 类别有数据但匹配 <50%，IC 乘 0.5x
- **Transport context**: 航班号/车次号必须在航班/火车关键词 200 字符内

### Completeness target_count (per type)
| Type | Key Categories | target_count |
|------|---------------|-------------|
| intercity | flights 2, trains 2, times 3, prices 3, pois 2 | |
| food_tour | restaurants **5**, dishes 3, routes 2, costs 2 | |
| business | transport 2, hotels 2, dining 2, costs 2, business 2 | |
| multiday | pois days×2, dining days, lodging days-1, budget 2 | |
| family_study | pois days×2, child 2, education 2, dining days-1, budget 2 | |

### Hard Constraints
| Constraint | Penalty | Trigger |
|-----------|---------|---------|
| format_valid | 0.15x | output < 200 chars |
| tool_info_used | 0x/0.05x | IC < 6/8 |
| poi_names_verified | 0.7x | <2 POI names |
| transport_grounded | 0.3x | fabricated IDs |

### LLM Score (50 pts, eval-time)
- 5 dimensions × 10, code coupling: `llm *= min(1.0, code / 30)`

## V7 Canonical — 3865 entries (2026-03-25)

| Type | Count |
|------|-------|
| intercity | 629 |
| food_tour | 625 |
| business | 606 |
| single_poi | 571 |
| hybrid | 508 |
| family_study | 471 |
| multiday | 455 |

- **IC-optimized prompt**: keyword+fact proximity → 测试 IC 25/25 满分（9/9 categories = 1.0）
- **Per-step think**: 每个 tool_call 和 plan 都有 `<think>` 块
- **Quality floor**: 全部 ≥45，新数据 ≥48
- **Validation**: 0 missing tool_call_id, 0 bad format, 100% audit pass
- **NW ratio**: 15.0% (with LW 12054). 需要 Trainer 控制 LW 或 repeat NW 到 19.7%

## Score History

| Version | Score | Key Change |
|---------|-------|-----------|
| v2.1-v2.8 | 1.5-12.6† | 早期迭代 |
| **v2.13b** | **25.13** | content=None 修复 |
| **v2.16** | **35.46** | GAME think-then-act |
| **v2.17a** | **42.34** | NW 19.7%, think 溢出 |
| v2.19 | 19.45 | Think 稀释 49% |
| v2.20 | 37.77 | NW ratio 12.8% |
| **v2.21** | **42.84** | **BEST.** NW 2966 + think |
| v2.22 | 21.38 | reasoning-parser + 旧数据 |
| v2.23 | 34.88 | LW 12054(48%) 稀释 NW |

†v2.7+ includes CHUTES LLM scoring (max 100).

### v2.23 Analysis
- **无 reasoning-parser 时 34.88**（有 reasoning-parser 时 19.45）
- 根因: LW 12054 占 48% 稀释 NW（v2.17a LW 只占 14%）
- Trainer 建议: 减 LW 到 ≤3000 或 repeat NW

### 提分到 50 的路径
1. **NW ratio ≥19%** — 最关键杠杆（数据侧: 增到 5000+ 或 Trainer 减 LW）
2. **IC-optimized plan format** — V7 prompt 让 keyword+fact 紧邻（已做）
3. **80-85% checkpoint** — late training 退化 6-8 分（训练侧）
4. **不用 reasoning-parser** — 已确认有害（训练侧）
5. **intercity 提分** — v2.21 最差类型(25.1)，已替换弱数据+增加高质量数据

## Format Requirements (HARD RULES)
1. `tokenizer.apply_chat_template(messages, tools=tools)` — Qwen3 native
2. Inference: `--tool-call-parser qwen25`, **不用** `--reasoning-parser qwen3`
3. System prompt / tool schema 必须匹配 eval 的中文版本
4. **Every assistant message 必须有 `<think>` block**
5. **Tool result 必须有 `tool_call_id`**
6. **content 不能是 None**
7. **`<tool_call>` 不能出现在 content 中**

## Data Generation Pipeline

```bash
# V7 pipeline — IC-optimized + streaming + per-step think
forge data navworld-gen -n 50 --model gpt-5.4 --type <type> -o output.jsonl
python3 scripts/navworld_quality_audit.py --threshold 48
```

Key files:
- `forge/data/navworld_gen.py` — IC-optimized prompt + streaming + think + validation
- `forge/data/navworld_prompts.py` — system prompt, tool schema, user prompts
- `forge/data/navworld_plans.py` — tool call sequences per type
- `scripts/navworld_quality_audit.py` — QQR code scoring
- `scripts/navworld_add_step_think.py` — batch add per-step think

## Key Learnings
- **IC proximity 是最大提分杠杆** — keyword+fact 在 500ch 内 = 满分, 分开写 = 20%
- **NW 占比 ~19.7% 最优** — 低了被稀释, 数据量要跟着总量增长
- **Think per step 必须** — 防 think 稀释 + 兼容 reasoning parser
- **数据质量 > 数量** — 1658 条(42.34) ≈ 2966 条(42.84), 边际收益递减
- **reasoning-parser 有害** — 不用时 34.88, 用时 19.45
- **80-85% checkpoint** — late training 退化确认

## Dead Ends (DO NOT REPEAT)
- **content=None**: Qwen3 can't tokenize
- **Empty think**: Model learns nothing
- **NW without think**: Gets diluted by non-think data
- **`<tool_call>` in content**: Breaks parser
- **Missing tool_call_id**: Chat template can't match
- **Non-streaming API**: Proxy 504
- **reasoning-parser qwen3**: Kills NW tool_call (v2.22)
- **keyword+fact 分开写**: Scorer proximity check 降到 20%
- **qwen-max data**: All <25
- **seq=16384**: Use 8192
