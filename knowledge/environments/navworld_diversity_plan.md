# NAVWORLD Diversity Expansion Plan

> Status: PHASE 1 EXECUTED (D8 complete — 397 entries merged to canonical 2026-03-19)
> Date: 2026-03-18 (design) / 2026-03-19 (Phase 1 execution)
> Depends on: navworld_quality_analysis.md (D1 findings)

---

## 1. Current 5 Templates Analysis

The quality analysis found exactly 5 query templates, each used ~448 times (near-uniform distribution). Here is what each template actually does:

### Template A: `intercity` (Transport Compare) — 20.2%

- **User prompt pattern**: "I plan to travel from {origin} to {destination}, departure {date}, budget {budget} CNY/person, preference: {pref}. Help me: 1) look up flights and trains 2) compare at least 3 options 3) recommend best 4) attraction suggestions"
- **Tool sequence**: `search_flights + search_train_tickets → poi_search + weather → direction → around_search`
- **Differentiation**: Transport-comparison-heavy. Always starts with transport, attractions secondary.

### Template B: `multiday` (Detailed Multi-day) — 20.1%

- **User prompt pattern**: "I plan to travel from {origin} to {destination} for {N}-day trip, date {date}, budget {budget} CNY. Interests: {interests}. Provide: daily schedule, dining, accommodation, routes, budget."
- **Tool sequence**: `poi_search + weather → poi_search + poi_search → search_flights + search_train_tickets → direction → around_search`
- **Differentiation**: Multi-poi-search heavy (3 poi_search calls: attractions, hotels, restaurants). Transport comes after POI research.

### Template C: `hybrid` (General Travel) — 19.8%

- **User prompt pattern**: "I plan to travel from {origin} to {destination} for {N} days. Date: {date}, budget: {budget} CNY, transport preference: {pref}. Interests: {interests}. Help me complete full travel plan."
- **Tool sequence**: `search_flights + search_train_tickets → poi_search + weather → poi_search + poi_search → direction → around_search`
- **Differentiation**: Nearly identical to multiday but starts with transport. Structurally redundant.

### Template D: `food_tour` (Food Trip) — 19.9%

- **User prompt pattern**: "I'm departing from {origin} for a {N}-day food tour in {destination}. Date: {date}, budget: {budget} CNY. Provide: train options, daily dining plan (3 meals + snacks), routes between restaurants, attractions, weather."
- **Tool sequence**: `poi_search("美食 餐厅") + weather → poi_search("小吃街") + around_search → search_train_tickets → direction`
- **Differentiation**: The ONLY template without search_flights (train-only). POI searches target food keywords. This explains the 80.1% flight coverage split.

### Template E: `business` (Business Trip) — 19.8%

- **User prompt pattern**: "I need to travel from {origin} to {destination} for business. Date: {date}, budget {budget} CNY/person, {pref}. Help me: flights vs rail, business hotels, weather, dining after work."
- **Tool sequence**: `search_flights + search_train_tickets → poi_search("商务酒店") + weather → poi_search("餐厅") → direction → around_search`
- **Differentiation**: Only template that searches specifically for business hotels. Otherwise structurally similar to intercity.

### Key Findings

1. **Three templates are structurally redundant**: intercity, hybrid, and business all follow `transport → poi → direction → around` with minor keyword differences. The model learns one pattern three times.
2. **Parameter variation, not query variation**: All 5 templates accept the same parameter types (origin, destination, date, budget). The "diversity" is city name swaps, not behavioral differences.
3. **All prompts are structured request lists**: Every user prompt is a numbered instruction list. Zero open-ended queries, zero conversational style, zero ambiguity.
4. **English prompts, not Chinese**: The current `problem_to_prompt()` generates English prompts (e.g., "I plan to travel from..."). The eval environment uses Chinese user queries. This is a language mismatch.
5. **Fixed tool counts**: Every template produces exactly 6-8 tool calls. No short sequences (2-3 tools) or long sequences (10+).

---

## 2. New Query Type Designs (20 types)

### Category A: Open-Ended Queries

#### A1: Weekend Escape (周末随便逛)

- **Description**: Vague weekend trip request with no specific destination. Model must suggest destinations and then plan.
- **Example prompt**: "这个周末想出去玩，从上海出发，预算2000块，两天一夜，去哪好？帮我安排一下。"
- **Expected tool sequence**: `weather(上海周边城市) → poi_search(推荐目的地景点) → search_train_tickets → poi_search(酒店) → around_search(餐厅) → direction`
- **Why it adds diversity**: Model must DECIDE a destination before planning. Current data always provides destination upfront. Teaches reasoning-first, tools-second.

#### A2: Route Planning (帮我规划路线)

- **Description**: User gives a list of places they want to visit; model must optimize the route order.
- **Example prompt**: "我在杭州，想去西湖、灵隐寺、宋城、龙井村、河坊街，帮我规划一个一天的最佳路线，包括吃饭的地方。"
- **Expected tool sequence**: `poi_search(西湖) → poi_search(灵隐寺) → poi_search(宋城) → poi_search(龙井村) → poi_search(河坊街) → direction(优化路线) → direction(第二段) → around_search(午餐) → weather`
- **Why it adds diversity**: Multiple sequential poi_search calls for known destinations (5+), then multiple direction calls to compute optimal ordering. Current data never does route optimization.

#### A3: Inspiration Request (不知道干嘛)

- **Description**: Extremely vague — user just wants suggestions.
- **Example prompt**: "最近压力好大，想找个地方放松一下，3天假，预算不限，有什么推荐的吗？"
- **Expected tool sequence**: `poi_search(度假胜地) → weather(候选城市1) → weather(候选城市2) → search_flights → poi_search(酒店/spa) → around_search → direction`
- **Why it adds diversity**: Multiple weather calls to compare candidates. Model must generate reasoning about WHY it recommends a destination.

### Category B: Multi-Turn Conversations

#### B1: Mid-Plan Requirement Change (改主意了)

- **Description**: User changes destination or budget after seeing initial research.
- **Example prompt**:
  - Turn 1: "帮我查一下北京到三亚的机票和酒店，下周五出发，4天。"
  - Turn 2 (after tool results): "三亚机票太贵了，换成厦门吧，其他要求不变。"
- **Expected tool sequence**: `search_flights(三亚) + search_train_tickets(三亚) → poi_search(三亚酒店) → [user changes] → search_flights(厦门) + search_train_tickets(厦门) → poi_search(厦门景点) → weather(厦门) → direction → around_search`
- **Why it adds diversity**: First multi-turn template. Model must abandon partial research and restart for new destination. Teaches adaptive replanning. Tool count reaches 9-11.

#### B2: Follow-Up Detail Request (再详细说说)

- **Description**: User asks for more detail on a specific part of the plan.
- **Example prompt**:
  - Turn 1: "帮我规划一个成都3日游。"
  - Turn 2: "第二天的行程太赶了，能不能把宽窄巷子和锦里安排在同一天？另外帮我查一下附近有什么好吃的火锅店。"
- **Expected tool sequence**: `poi_search + weather + poi_search + direction + around_search → [user follow-up] → around_search(火锅店, near 宽窄巷子) → direction(revised route)`
- **Why it adds diversity**: Second tool-calling phase triggered by follow-up. Model learns incremental planning.

#### B3: Group Negotiation (朋友意见不同)

- **Description**: User relays conflicting preferences from group members.
- **Example prompt**:
  - Turn 1: "我们4个人从广州出发玩3天，我想去海边，闺蜜想逛街购物，有没有两全的方案？"
  - Turn 2: "她说不想去厦门，太远了，有没有近一点的？"
- **Expected tool sequence**: `poi_search(海边+购物目的地) → search_train_tickets(多个候选) → weather → poi_search(景点) → poi_search(商圈) → direction → around_search`
- **Why it adds diversity**: Constraint satisfaction across conflicting requirements. Multiple candidate evaluations.

### Category C: Error Handling & Edge Cases

#### C1: No Direct Transport (没有直达)

- **Description**: Query for a city pair with no direct flights, forcing alternative routing.
- **Example prompt**: "我从福州想去张家界，下周三出发，3天，预算3000，帮我查查怎么去最方便。"
- **Expected tool sequence**: `search_flights(福州→张家界, returns empty/少) → search_train_tickets(福州→张家界) → search_flights(福州→长沙) → search_train_tickets(长沙→张家界) → poi_search(张家界景点) → weather → direction → around_search`
- **Why it adds diversity**: Retry/fallback pattern. First search returns poor results, model must find alternative routing via transfer city. This is the most critical missing pattern.

#### C2: Bad Weather Adaptation (天气不好怎么办)

- **Description**: Weather query returns rain/storm, model should adapt outdoor plans to indoor alternatives.
- **Example prompt**: "下周去桂林玩3天，帮我规划行程，如果下雨的话有什么室内备选方案？"
- **Expected tool sequence**: `weather(桂林) → poi_search(桂林景点) → poi_search(桂林室内景点/博物馆) → search_train_tickets → direction → around_search → poi_search(雨天备选)`
- **Why it adds diversity**: Conditional branching based on weather tool result. Model must plan A/B alternatives. Also teaches weather-dependent reasoning.

#### C3: Sold-Out / Empty Results (搜不到结果)

- **Description**: Some POI searches or transport searches return empty results. Model must handle gracefully.
- **Example prompt**: "帮我查一下明天从昆明到丽江的火车票，还有丽江古城附近的民宿。"
- **Expected tool sequence**: `search_train_tickets(昆明→丽江) → poi_search(丽江古城民宿, may return limited) → around_search(住宿, fallback) → poi_search(丽江景点) → weather → direction`
- **Why it adds diversity**: Model learns to use around_search as fallback when poi_search returns insufficient results. Current data has ZERO empty-result handling.

#### C4: Ambiguous Request Requiring Clarification (信息不完整)

- **Description**: User gives incomplete info (no date, no budget, vague destination).
- **Example prompt**: "想去南方玩几天。"
- **Expected tool sequence**: Model should first ask clarifying questions, then after user provides more info: `weather → search_flights → poi_search → direction → around_search`
- **Why it adds diversity**: Model learns to ask questions BEFORE calling tools, rather than guessing. Current data always provides complete parameters.

### Category D: Special Needs

#### D1: Accessibility Travel (无障碍出行)

- **Description**: User has mobility constraints, needs wheelchair-accessible venues.
- **Example prompt**: "我爸腿脚不方便，坐轮椅，想带他从北京去西安玩3天，帮我找一些无障碍的景点和酒店。"
- **Expected tool sequence**: `search_train_tickets(无障碍座) → poi_search(西安无障碍景点) → poi_search(无障碍酒店) → weather → direction(transit mode) → around_search(餐厅)`
- **Why it adds diversity**: POI search keywords include accessibility terms. Direction mode prefers transit over walking. Plan must address physical limitations.

#### D2: Pet-Friendly Travel (带宠物出行)

- **Description**: User traveling with pet, needs pet-friendly accommodations.
- **Example prompt**: "带我家金毛从上海去杭州玩周末，要能带狗进去的酒店和景点，预算1500。"
- **Expected tool sequence**: `search_train_tickets → poi_search(杭州宠物友好酒店) → poi_search(杭州允许宠物景点) → weather → around_search(宠物公园) → direction`
- **Why it adds diversity**: Specialized search keywords. Model must filter recommendations by pet-friendliness constraint.

#### D3: Red Tourism (红色旅游)

- **Description**: Patriotic/revolutionary history tourism, common in Chinese travel context.
- **Example prompt**: "单位组织红色教育活动，从长沙出发去韶山+井冈山，2天，20人，预算每人800。"
- **Expected tool sequence**: `poi_search(韶山红色景点) → poi_search(井冈山红色景点) → search_train_tickets(长沙→韶山) → search_train_tickets(韶山→井冈山) → weather → direction → around_search(团餐)`
- **Why it adds diversity**: Group travel (20 people) changes transport and dining calculations. Multiple inter-city transfers in one trip. Niche but culturally important category.

#### D4: Photography Route (摄影路线)

- **Description**: User wants to visit photogenic spots at optimal times (sunrise, sunset, night views).
- **Example prompt**: "我是摄影爱好者，想去厦门拍3天，帮我安排拍摄路线，要包括日出日落机位和夜景。"
- **Expected tool sequence**: `weather(厦门, check cloud cover) → poi_search(厦门观景台/摄影点) → poi_search(厦门日出点) → poi_search(厦门夜景) → direction(多段路线) → around_search(咖啡馆休息) → direction`
- **Why it adds diversity**: Multiple direction calls for multi-leg routes. Time-sensitive planning (sunrise/sunset). Weather is decision-critical, not just informational.

### Category E: Constraint-Based Trips

#### E1: Ultra-Budget Trip (穷游)

- **Description**: Extremely tight budget forces creative solutions.
- **Example prompt**: "学生党，从武汉去重庆玩3天，总共只有500块（含车票），怎么玩？"
- **Expected tool sequence**: `search_train_tickets(最便宜) → poi_search(重庆免费景点) → poi_search(青旅/便宜住宿) → weather → around_search(便宜小吃) → direction(公交/步行)`
- **Why it adds diversity**: Budget constraint forces different POI search terms (free, cheap). Direction mode should prefer walking/transit over driving. Plan must include cost optimization reasoning.

#### E2: Half-Day City Tour (半日游)

- **Description**: User only has 4-6 hours in a city (e.g., during layover).
- **Example prompt**: "我在南京转机，有5个小时空闲，想在市区逛逛，推荐一下去哪？"
- **Expected tool sequence**: `poi_search(南京机场附近景点) → direction(机场到景点) → poi_search(快餐) → direction(景点回机场) → weather`
- **Why it adds diversity**: Short trip = fewer tools (4-5 calls). Time constraint is the primary filter. Direction travel time becomes the deciding factor.

#### E3: Extended Trip (长途深度游)

- **Description**: Long trip (7+ days) requiring multi-city itinerary.
- **Example prompt**: "想从北京出发走丝绸之路，西安→兰州→敦煌→乌鲁木齐，10天，预算8000。"
- **Expected tool sequence**: `search_train_tickets(北京→西安) → search_train_tickets(西安→兰州) → search_train_tickets(兰州→敦煌) → search_flights(敦煌→乌鲁木齐) → poi_search(每城景点, 4次) → weather(多城) → direction(多段) → around_search(多城餐厅)`
- **Why it adds diversity**: Highest tool count (12-16 calls). Multiple transport legs. Multiple weather/poi calls for different cities. Tests the model's ability to manage complex multi-step plans.

### Category F: Seasonal & Event-Based

#### F1: Cherry Blossom / Seasonal Viewing (赏花季)

- **Description**: Timing-sensitive trip for seasonal natural events.
- **Example prompt**: "3月底想去武汉看樱花，从杭州出发，2天1夜，帮我安排行程，武大樱花什么时候开最好？"
- **Expected tool sequence**: `weather(武汉, check temperature/rain) → poi_search(武汉樱花景点) → poi_search(武汉大学) → search_train_tickets → poi_search(酒店) → direction → around_search(餐厅)`
- **Why it adds diversity**: Weather check becomes essential for bloom prediction. Seasonal timing adds a reasoning dimension absent from current data.

#### F2: Festival Trip (节日活动)

- **Description**: Trip centered around a specific festival or event.
- **Example prompt**: "想去哈尔滨看冰雪大世界，1月中旬从广州出发，4天，需要注意什么？穿什么衣服？"
- **Expected tool sequence**: `weather(哈尔滨, January = extreme cold) → search_flights(广州→哈尔滨) → search_train_tickets → poi_search(冰雪大世界) → poi_search(哈尔滨室内景点) → poi_search(酒店) → direction → around_search(东北菜)`
- **Why it adds diversity**: Extreme weather affects entire plan (indoor/outdoor balance, clothing). Model must provide safety/preparation advice beyond just itinerary.

### Category G: International & Rural

#### G1: International Destination (出境游)

- **Description**: International trip — flight-only, no train option, different considerations.
- **Example prompt**: "从上海去东京玩5天，预算1万，想去浅草寺、秋叶原、富士山，帮我规划。"
- **Expected tool sequence**: `search_flights(上海→东京) → poi_search(东京浅草寺) → poi_search(秋叶原) → poi_search(富士山) → weather(东京) → direction → around_search(拉面店)`
- **Why it adds diversity**: No train option for international routes (search_train_tickets should be skipped or return empty). Model must handle this gracefully. Note: AMap POI data for international cities may be limited, teaching empty-result handling naturally.

#### G2: Rural / Small City (小众目的地)

- **Description**: Trip to a small city/county that may have limited POI data.
- **Example prompt**: "想去贵州荔波小七孔玩2天，从贵阳出发，怎么去？附近有住的地方吗？"
- **Expected tool sequence**: `poi_search(荔波小七孔) → search_train_tickets(贵阳→荔波, limited) → poi_search(荔波酒店, few results) → around_search(小七孔附近住宿) → weather(荔波) → direction`
- **Why it adds diversity**: Small cities return sparse POI results. Model must work with limited data rather than abundant results. around_search becomes essential fallback.

---

## 3. Tool-Call Sequence Diversity

### Current state: 5 sequences

All current sequences follow a rigid pattern of 6-8 calls with parallel batches. Below are 12 new sequence patterns that introduce meaningful structural diversity.

### New Sequence Patterns

| # | Pattern Name | Tool Sequence | Call Count | Trigger |
|---|-------------|---------------|------------|---------|
| S1 | Short scout | `weather → poi_search → direction` | 3 | Half-day tour (E2) |
| S2 | Destination selection | `weather(city1) → weather(city2) → poi_search(chosen) → search_train → direction → around` | 6 | Open-ended (A1, A3) |
| S3 | Route optimizer | `poi_search ×5 → direction ×3 → around_search → weather` | 10 | Route planning (A2) |
| S4 | Transport fallback | `search_flights(empty) → search_train → search_flights(alt route) → search_train(alt) → poi_search → weather → direction → around` | 8-10 | No direct transport (C1) |
| S5 | Weather-conditional | `weather(rain) → poi_search(indoor) → poi_search(outdoor backup) → search_train → direction → around` | 6-7 | Bad weather (C2) |
| S6 | Multi-city chain | `search_train ×4 → poi_search ×4 → weather ×3 → direction ×3 → around ×2` | 16 | Extended trip (E3) |
| S7 | Retry with around | `poi_search(sparse) → around_search(fallback) → poi_search(alt keyword) → weather → direction` | 5 | Rural destination (G2) |
| S8 | Two-phase (multi-turn) | `[Phase 1: search_flights + poi_search + weather] → [user changes] → [Phase 2: search_flights(new) + poi_search(new) + weather + direction + around]` | 8-11 | Requirement change (B1) |
| S9 | Budget-filtered | `search_train(cheapest) → poi_search(免费景点) → around_search(小吃) → direction(walking/transit)` | 4 | Ultra-budget (E1) |
| S10 | Photography multi-leg | `weather → poi_search ×3(sunrise/sunset/night) → direction ×3(between spots) → around_search` | 8-10 | Photography (D4) |
| S11 | Group multi-constraint | `poi_search(海边) → poi_search(商圈) → search_train ×2(candidates) → weather ×2 → direction → around` | 9 | Group negotiation (B3) |
| S12 | Clarification-first | `[no tools] → [user provides more info] → weather → search_flights + search_train → poi_search → direction → around` | 5-7 | Ambiguous request (C4) |

### Diversity metrics comparison

| Metric | Current | Target |
|--------|---------|--------|
| Unique sequences | 5 | 17+ |
| Tool call range | 6-8 | 3-16 |
| Std dev of call count | 0.9 | 3.0+ |
| Templates with retry/fallback | 0 | 3+ |
| Templates with multi-turn | 0 | 3+ |
| Templates skipping a tool type | 0 (except flights in food_tour) | 5+ |

---

## 4. Generation Cost Estimate

### Per-entry cost model

Each entry requires:
- **AMap API calls**: 5-16 calls (free tier: 5000/day for most endpoints)
- **DashScope LLM calls**: 1 call for final plan generation (+ 1 retry if quality gate fails)
  - Input: ~3000-5000 tokens (system + user + tool results summary)
  - Output: ~800-2000 tokens (final plan)

### Token cost per entry

| Component | Input Tokens | Output Tokens | Cost (qwen3-max) |
|-----------|-------------|---------------|-------------------|
| Final plan generation | ~4000 | ~1200 | ~0.008 CNY |
| Quality retry (30% rate) | ~5000 | ~1200 | ~0.003 CNY (amortized) |
| **Total per entry** | | | **~0.011 CNY** |

DashScope qwen3-max pricing: input 0.002 CNY/1k tokens, output 0.006 CNY/1k tokens (approximate, varies by plan).

### Batch cost estimate

| Phase | New Types | Entries/Type | Total Entries | LLM Cost | AMap Calls |
|-------|-----------|-------------|---------------|----------|------------|
| Phase 1 (priority) | 8 | 50 | 400 | ~4.4 CNY | ~3,200 |
| Phase 2 (expand) | 8 | 100 | 800 | ~8.8 CNY | ~8,000 |
| Phase 3 (full) | 20 | 150 | 3,000 | ~33 CNY | ~30,000 |

**Total estimated cost for full expansion: ~46 CNY (~$6.30 USD)**. Cost is negligible; the bottleneck is engineering time for new templates and tool-plan logic.

### Minimum viable diversity

To avoid the model memorizing per-type recipes, each new type needs at minimum **30 entries** with parameter variation (different cities, dates, budgets). With 20 types at 30 entries each, that is 600 new entries minimum for meaningful diversity gain.

---

## 5. Implementation Plan

### Phase 1: High-Impact Quick Wins (8 types, ~1 day engineering)

**Priority**: Types that fix the most critical gaps identified in the quality analysis.

| Type | Why First | Changes Needed |
|------|-----------|----------------|
| C1: No Direct Transport | Adds retry/fallback (currently 0%) | New TOOL_PLAN with conditional fallback logic |
| C3: Sold-Out / Empty Results | Adds error handling (currently 0%) | Inject empty results into pipeline; new TOOL_PLAN |
| E2: Half-Day Tour | Adds short sequences (currently 0 entries <6 calls) | New TOOL_PLAN with 3-5 calls |
| A1: Weekend Escape | Adds open-ended queries (currently 0%) | New problem type + prompt template |
| E1: Ultra-Budget | Adds budget-constrained reasoning | New prompt template with budget-aware POI keywords |
| B1: Mid-Plan Change | Adds multi-turn (currently 0%) | New multi-phase generation logic in `generate_conversation` |
| C2: Bad Weather | Adds conditional branching | Weather-dependent TOOL_PLAN branching |
| D4: Photography Route | Adds multi-leg direction calls | TOOL_PLAN with 3+ direction calls |

#### Code changes for Phase 1

**1. `navworld_prompts.py` changes:**

- Add `PROBLEM_TYPES` entries: `"weekend_escape"`, `"half_day"`, `"budget_trip"`, `"no_direct"`, `"bad_weather"`, `"photo_route"`, `"mid_change"`, `"empty_result"`
- Add corresponding `problem_to_prompt()` branches generating **Chinese** prompts (fix the English prompt issue)
- Expand `CITY_PAIRS_*` with:
  - Indirect pairs: `("福州", "张家界")`, `("昆明", "敦煌")`, `("南宁", "丽江")`
  - Short-distance pairs: `("杭州", "乌镇")`, `("成都", "乐山")`, `("长沙", "凤凰")`
  - Add 15+ new cities to `MAJOR_CITIES`: 洛阳, 大同, 荔波, 凤凰, 乌镇, 婺源, 阳朔, 平遥, 敦煌, 泉州, 开封, 济南, 绍兴, 镇江, 太原
- Add Chinese interest keywords: `"自然风光"`, `"历史文化"`, `"美食探索"`, `"摄影打卡"`, `"亲子游乐"`, etc. (replace current English interests)

**2. `navworld_gen.py` changes:**

- Add new `TOOL_PLANS` entries for each new type
- Add conditional logic in `generate_conversation`:
  - For `"no_direct"`: if first `search_flights` returns empty/few, trigger fallback to transfer city
  - For `"bad_weather"`: check weather result for rain keywords, branch to indoor POI search
  - For `"empty_result"`: if `poi_search` returns <2 results, trigger `around_search` fallback
  - For `"mid_change"`: implement two-phase generation with user turn injection between phases
- Add `_inject_empty_result()` helper to simulate empty API responses for training robustness
- Change tool call ID generation to include `task_id` in hash input (fix reused ID issue)

**3. New generation parameter in `generate_problem()`:**

- Add `"language": "zh"` flag (all new types generate Chinese prompts)
- Add `"multi_turn": True/False` flag
- Add `"min_tools"` / `"max_tools"` per type to enforce variable tool counts

### Phase 2: Diversity Expansion (8 more types, ~1 day engineering)

| Type | Depends On |
|------|-----------|
| A2: Route Planning | Phase 1 multi-poi logic |
| A3: Inspiration Request | Phase 1 Chinese prompts |
| B2: Follow-Up Detail | Phase 1 multi-turn logic |
| B3: Group Negotiation | Phase 1 Chinese prompts |
| D1: Accessibility | Phase 1 keyword expansion |
| D3: Red Tourism | Phase 1 group + multi-city |
| E3: Extended Trip | Phase 1 multi-city logic |
| F2: Festival Trip | Phase 1 weather-conditional |

### Phase 3: Full Coverage (remaining 4 types + scale)

| Type | Notes |
|------|-------|
| C4: Ambiguous Request | Requires clarification-turn logic |
| D2: Pet-Friendly | Keyword variation only |
| F1: Cherry Blossom | Seasonal + weather |
| G1: International | May need AMap international POI testing |
| G2: Rural / Small City | Relies on Phase 1 empty-result handling |

Scale each type to 100-150 entries. Target total: 3000+ new entries combined with existing 2248 (filtered for quality).

### Integration with existing data

The new entries should be **added to** (not replace) the existing 2248 entries, after:
1. Filtering existing data to keep only entries with POI grounding >= 60%
2. Fixing tool call IDs in existing data (add entry index to hash)
3. Converting existing English prompts to Chinese (for consistency)

Target final dataset size: ~4000-5000 entries with 20+ query types, 15+ tool sequences, 40+ cities.

### Validation checklist (before training)

- [ ] Each new type has >= 30 entries
- [ ] Tool call count distribution has std dev >= 2.5
- [ ] At least 3 types have retry/fallback sequences
- [ ] At least 3 types have multi-turn conversations
- [ ] No type exceeds 15% of total dataset
- [ ] All user prompts are in Chinese
- [ ] Tool call IDs are unique across all entries
- [ ] At least 5 entries per type have empty/error tool responses
- [ ] Plan length std dev >= 400 chars (vs current 160)
