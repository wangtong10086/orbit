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

## V8 Canonical — 4170 entries (2026-03-27)

| Type | Count |
|------|-------|
| business | 629 |
| food_tour | 629 |
| family_study | 624 |
| intercity | 614 |
| hybrid | 583 |
| single_poi | 571 |
| multiday | 520 |

- **IC-optimized prompt**: keyword+fact proximity
- **Per-step think**: 每个 tool_call 和 plan 都有 `<think>` 块
- **NW ratio in v2.25**: 17.4% (4148/23783). Need 5000+ for 19%+

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
| **v2.25** | **40.57** | NW 4148(17.4%), LW 8816(37%), ckpt-400 |

†v2.7+ includes CHUTES LLM scoring (max 100).

### v2.25 Analysis (2026-03-27)
- **85 tasks, avg 40.57** — code 25.54/50, LLM 15.98/50
- **LLM coupling bottleneck**: 62% tasks code<30 → LLM capped. When code≥30, LLM avg 28.7 vs 8.3
- **Weakest types**: food_tour (35.0), multiday (35.3), intercity (36.5)
- **Strongest**: business (47.9), family_study (44.4)
- **4 near-zero tasks**: format_valid(3), tool_info_used(3) failures
- **vs v2.17a (42.34)**: 1.77pt gap likely from NW ratio 17.4% vs 19.7%

### 提分到 45+ 的路径
1. **提高 code score → 解锁 LLM** — code<30 = LLM 被截断, 最大杠杆
2. **food_tour/multiday/intercity 补强** — 最弱三个类型, 需更高IC密度数据
3. **NW ratio ≥19%** — 需 ~5000 条 或 Trainer 减 LW
4. **不用 reasoning-parser** — 已确认有害（训练侧）
5. **Quality floor ≥35** — 移除所有 code<35 数据

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
