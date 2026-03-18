# NAVWORLD Data Quality Analysis

**Dataset**: `data/canonical/navworld.jsonl`
**Entries analyzed**: 2248
**Analysis date**: 2026-03-18

---

## 1. Plan Quality Scoring

### 1.1 Final Plan Length Distribution

| Metric | Value |
|--------|-------|
| Count | 2248 |
| Mean | 1882 chars |
| Median | 1870 chars |
| Std Dev | 160 chars |
| Min | 1413 chars |
| Max | 2611 chars |
| P5 | 1629 chars |
| P25 | 1774 chars |
| P75 | 1986 chars |
| P95 | 2156 chars |

**Length buckets:**

| Range (chars) | Count | % |
|---------------|-------|---|
| 0 (no plan) | 0 | 0.0% |
| 1-499 | 0 | 0.0% |
| 500-999 | 0 | 0.0% |
| 1000-1999 | 1748 | 77.8% |
| 2000-2999 | 500 | 22.2% |
| 3000-4999 | 0 | 0.0% |
| 5000+ | 0 | 0.0% |

**Observation**: All plans fall in a narrow 1413-2611 char band with std dev of only 160 chars. This is suspiciously uniform — real travel plans would have much higher variance depending on trip complexity (1-day vs 5-day, business vs leisure).

### 1.2 Specificity Analysis

**POI Grounding** (POIs from tool results referenced in final plan):

- Entries with POI data: 2248 (100%)
- Mean POI reference rate: 59.8%
- Median POI reference rate: 55.0%
- Entries with 0% POI grounding: 0
- Entries with 100% POI grounding: 142 (6.3%)
- Entries with <20% POI grounding: 2 (0.1%)
- Entries with >=80% POI grounding: 530 (23.6%)

**Budget/cost mentions**: 2248 entries (100.0%)

**Day-by-day structure**: 1480 entries (65.8%)

**Specific time mentions per entry:**

| Count | Entries | % |
|-------|---------|---|
| 0 | 0 | 0.0% |
| 1-3 | 17 | 0.8% |
| 4-6 | 242 | 10.8% |
| 7-10 | 407 | 18.1% |
| 11+ | 1582 | 70.4% |

**Logical sequence markers per entry:**

| Count | Entries | % |
|-------|---------|---|
| 0 | 228 | 10.1% |
| 1-3 | 568 | 25.3% |
| 4-7 | 690 | 30.7% |
| 8+ | 762 | 33.9% |

### 1.3 Logical Coherence

All plans follow a consistent structure: transport comparison → sightseeing/activity plan → dining → budget breakdown → tips. This is correct for the domain but overly rigid — 100% of entries follow the same pattern, leaving no room for the model to learn flexible response styles.

---

## 2. Tool-Call Efficiency

### 2.1 Tool Call Count Distribution

| Metric | Value |
|--------|-------|
| Mean | 7.0 |
| Median | 7 |
| Min | 6 |
| Max | 8 |
| Std Dev | 0.9 |

**All 2248 entries have exactly 6-8 tool calls.** Zero entries have fewer than 6 or more than 8. This is extremely uniform.

| Bucket | Count | % |
|--------|-------|---|
| 0-2 | 0 | 0.0% |
| 3-5 | 0 | 0.0% |
| 6-8 | 2248 | 100.0% |
| 9-12 | 0 | 0.0% |
| 13-16 | 0 | 0.0% |
| 17+ | 0 | 0.0% |

### 2.2 Tool Type Usage

| Tool | Total Calls | Entries Using | % |
|------|-------------|---------------|---|
| poi_search | 4941 | 2248 | 100.0% |
| search_train_tickets | 2248 | 2248 | 100.0% |
| weather | 2248 | 2248 | 100.0% |
| direction | 2248 | 2248 | 100.0% |
| around_search | 2248 | 2248 | 100.0% |
| search_flights | 1800 | 1800 | 80.1% |

Every entry uses poi_search, search_train_tickets, weather, direction, and around_search. The only variation is whether search_flights is included (80.1% yes, 19.9% no — perfectly matching the food_trip template which uses train-only).

### 2.3 Tool Diversity Per Entry

| Unique Tool Types | Entries | % |
|-------------------|---------|---|
| 5 | 448 | 19.9% |
| 6 | 1800 | 80.1% |

Only two possible diversity values exist across all 2248 entries.

### 2.4 Redundant Calls

- Entries with redundant calls (same tool + same args): **0** (0.0%)
- Total redundant calls: **0**

### 2.5 Search-to-Navigation Conversion

- Entries with poi_search/around_search: **2248** (100.0%)
- Entries with direction calls: **2248** (100.0%)
- Entries with both search AND direction: **2248** (100.0%)
- Entries with search but NO direction: **0**

Perfect conversion rate — every entry that searches also navigates. This is good for teaching the workflow but unrealistically perfect.

### 2.6 POI Reference Rate (Unused Tool Results)

- Mean POI reference rate in final plan: **59.8%**
- Entries with <20% POI reference rate: **2** (0.1%)
- Entries with >=80% POI reference rate: **530** (23.6%)

~40% of POIs returned by tools go unreferenced in the final plan. This is expected (not all search results are relevant), but could teach the model to ignore tool results.

### 2.7 Tool Call Sequence Patterns

Only **5 unique tool call sequences** exist across all 2248 entries:

| Sequence Pattern | Count | % |
|-----------------|-------|---|
| flights+train → poi+weather → direction → around_search | 455 | 20.2% |
| poi+weather → poi+poi → flights+train → direction+around | 452 | 20.1% |
| flights+train → poi+weather → poi+poi → direction+around | 448 | 19.9% |
| poi+weather → around+poi → train → direction | 448 | 19.9% |
| flights+train → poi+weather → poi → direction+around | 445 | 19.8% |

Each sequence maps almost exactly to one of the 5 query templates. The model will learn exactly 5 tool-calling recipes, not general tool-calling reasoning.

### 2.8 Reused Tool Call IDs (Critical Finding)

**1,331 tool call IDs are reused across multiple entries.** The most reused IDs:

| Tool Call ID | Reused In |
|-------------|-----------|
| call_e7a9b2da | 173 entries |
| call_a2c3ad99 | 149 entries |
| call_daec655b | 143 entries |
| call_a7cf4af9 | 143 entries |
| call_d49c8a28 | 138 entries |

This strongly indicates the data was generated from a small set of templates with parametric variation (city names, dates, budgets swapped in). The underlying conversation structure is shared across many entries.

---

## 3. POI Category Coverage

### 3.1 POI Type Distribution (Top 20)

| POI Type | Count |
|----------|-------|
| 中餐厅 | 24919 |
| 餐饮服务 | 20996 |
| 风景名胜 | 10125 |
| 宾馆酒店 | 7702 |
| 住宿服务 | 6775 |
| 旅馆招待所 | 3321 |
| 外国餐厅 | 2834 |
| 快餐厅 | 2485 |
| 公园广场 | 2261 |
| 特色商业街 | 2248 |
| 餐饮相关场所 | 2119 |
| 餐饮相关 | 2119 |
| 购物服务 | 1652 |
| 住宿服务相关 | 1628 |
| 公园 | 1338 |
| 国家级景点 | 1163 |
| 火锅店 | 939 |
| 海鲜酒楼 | 910 |
| 经济型连锁酒店 | 816 |
| 特色/地方风味餐厅 | 742 |

Dining-related POIs dominate heavily (中餐厅 + 餐饮服务 alone = 45.9k of total). This reflects the data's bias toward food trips (28.2%) and the around_search queries focusing on restaurants.

### 3.2 Category Diversity Per Entry

| Diversity | Entries | % |
|-----------|---------|---|
| 0 types | 0 | 0.0% |
| 1 type | 0 | 0.0% |
| 2-3 types | 0 | 0.0% |
| 4-5 types | 0 | 0.0% |
| 6+ types | 2248 | 100.0% |

Every single entry has 6+ POI types. Zero entries have low diversity. This is again suspiciously uniform.

---

## 4. Quality Tiering

### Scoring Components (max 13 points)

- Plan length: 0-3 pts (thresholds: 500 / 1000 / 2000 chars)
- POI grounding rate: 0-3 pts (thresholds: >0% / >30% / >50% referenced)
- Day-by-day structure: 0-1 pt
- Sequence markers (>=5): 0-1 pt
- Specific time mentions (>=3): 0-1 pt
- Distance/duration mentions (>=2): 0-1 pt
- Tool diversity (>=3 types): 0-1 pt
- Budget mention: 0-1 pt

**Tier thresholds**: HIGH >= 8, MEDIUM >= 5, LOW < 5

### Distribution

| Tier | Count | % |
|------|-------|---|
| HIGH | 2220 | 98.8% |
| MEDIUM | 28 | 1.2% |
| LOW | 0 | 0.0% |

### Score Distribution

| Score | Count | Tier |
|-------|-------|------|
| 7 | 28 | MEDIUM |
| 8 | 314 | HIGH |
| 9 | 403 | HIGH |
| 10 | 479 | HIGH |
| 11 | 740 | HIGH |
| 12 | 284 | HIGH |

The data is overwhelmingly high quality by these metrics. The 28 MEDIUM entries (score=7) are all business trip queries with slightly lower POI grounding rates.

### Example Entries by Tier

#### HIGH Tier Examples

| Entry | Score | Plan Len | POIs Ref'd | Tools | Query Preview |
|-------|-------|----------|------------|-------|---------------|
| 5 | 12 | 2100 | 10/10 | 6 | 北京→昆明, 2225元/人, 速度优先 |
| 10 | 12 | 2156 | 10/10 | 6 | 深圳→厦门, 1346元/人, 经济优先 |
| 25 | 12 | 2260 | 10/10 | 6 | 南京→苏州, 3145元/人, 速度优先 |
| 42 | 12 | 2023 | 10/10 | 6 | 北京→三亚, 1190元/人, 舒适优先 |
| 45 | 12 | 2409 | 10/10 | 6 | 上海→南京, 4687元/人, 经济优先 |

#### MEDIUM Tier Examples (all 28)

| Entry | Score | Plan Len | POIs Ref'd | Tools | Query Preview |
|-------|-------|----------|------------|-------|---------------|
| 9 | 7 | 1808 | 6/15 | 7 | 北京→天津出差, 567元/人, 速度优先 |
| 115 | 7 | 1716 | 4/15 | 7 | 北京→昆明出差, 1499元/人, 经济优先 |
| 153 | 7 | 1862 | 5/20 | 8 | 北京→青岛1天, 1821元, 摄影打卡 |
| 159 | 7 | 1794 | 4/15 | 6 | 成都→西安美食1天, 2081元 |
| 181 | 7 | 1975 | 3/15 | 7 | 北京→大连出差, 4389元/人, 舒适优先 |

The MEDIUM entries are business trips and 1-day trips with more POIs returned but fewer referenced (lower grounding). No LOW tier entries exist.

---

## 5. Anomaly Detection

### 5.1 Missing Final Plans

Entries with no final plan text: **0**

### 5.2 Unusually Short Plans (<200 chars)

Count: **0** (minimum is 1413 chars)

### 5.3 Unusually Long Plans (>mean + 2*std = 2202 chars)

Count: **62** (2.8%)

| Entry | Length | Entry | Length |
|-------|--------|-------|--------|
| 1853 | 2611 | 944 | 2441 |
| 1513 | 2569 | 1464 | 2436 |
| 659 | 2515 | 45 | 2409 |
| 1150 | 2494 | 279 | 2374 |

These are not concerning — they represent multi-day trips with slightly more detail.

### 5.4 Near-Duplicate Plans

- Exact first-200-char duplicates: **0** groups
- Entries sharing first sentence (>2 entries): **0** groups

While no plans are textually identical, the structural similarity is very high (see Section 6).

### 5.5 Tool Response Errors

- Entries with error responses: **0**
- Entries with empty tool responses (`[]`): **13** (0.6%)
  - Entry indices: 683, 888, 893, 923, 1027, 1182, 1417, 1682, 1727, 1922, 1982, 1992, 2237
  - All 13 are `around_search` calls for 苏州 restaurants returning empty results
  - These entries still produce valid plans, ignoring the empty result

### 5.6 Extreme Tool Call Counts

- Entries with <=2 tool calls: **0**
- Entries with >20 tool calls: **0**
- Range is exactly 6-8 for all entries

---

## 6. Deep Analysis: Template Uniformity

This section documents the most significant quality concern: the dataset is generated from exactly **5 query templates** with parametric variation.

### 6.1 Query Templates

| Template | Description | Count | % |
|----------|-------------|-------|---|
| A: Transport Compare | "至少对比3种出行方案" | 455 | 20.2% |
| B: Detailed Multi-day | "每天的景点安排和路线规划" | 452 | 20.1% |
| C: Business Trip | "查询航班和高铁，对比价格和时间" | 445 | 19.8% |
| D: General Travel | "往返交通方案（至少对比2种方案）" | 448 | 19.9% |
| E: Food Trip | "每天的餐饮安排（早中晚+小吃）" | 448 | 19.9% |

Each template is used almost exactly 448 times (±7), confirming systematic generation.

### 6.2 Query Parameter Variation

**Origin cities** (only 10 unique):

| City | Count | % |
|------|-------|---|
| 北京 | 657 | 29.2% |
| 上海 | 429 | 19.1% |
| 广州 | 252 | 11.2% |
| 杭州 | 210 | 9.3% |
| 成都 | 203 | 9.0% |
| 福州 | 107 | 4.8% |
| 南京 | 105 | 4.7% |
| 深圳 | 96 | 4.3% |
| 武汉 | 95 | 4.2% |
| 昆明 | 94 | 4.2% |

**Destination cities**: ~25 unique (厦门 234, 西安 170, 长沙 149, 成都 92, etc.)

**Budget**: Uniformly distributed 502-5000 CNY (mean 2774, std 1303)

**Trip duration** (for multi-day templates):

| Days | Count | % |
|------|-------|---|
| 1 | 183 | 8.1% |
| 2 | 184 | 8.2% |
| 3 | 183 | 8.1% |
| 4 | 184 | 8.2% |
| 5 | 162 | 7.2% |

Note: Only entries from templates B and D have explicit day counts (896 total, 40%).

**User preferences**:

| Preference | Count | % |
|------------|-------|---|
| (not specified) | 1348 | 60.0% |
| 舒适优先 | 313 | 13.9% |
| 速度优先 | 294 | 13.1% |
| 经济优先 | 293 | 13.0% |

**Query types within detailed template:**

| Interest | Count |
|----------|-------|
| 户外运动 | ~20 per interest |
| 博物馆 | ~19 |
| 摄影打卡 | ~136 total |
| 亲子游乐 | ~127 total |
| etc. | evenly distributed |

### 6.3 Inter-Plan Similarity

Jaccard trigram similarity across 500 random plan pairs:

| Metric | Value |
|--------|-------|
| Mean | 0.096 |
| Median | 0.089 |
| P25 | 0.079 |
| P75 | 0.106 |
| Max | 0.272 |

While plans are not textually identical, the structural template is shared. Plans are differentiated only by:
1. City names and POI names (from tool responses)
2. Specific prices/times (from tool responses)
3. Day count variation

### 6.4 Plan Structure Patterns

| Section Combination | Count | % |
|--------------------|-------|---|
| transport + accommodation + dining + sightseeing + budget + tips | 1634 | 72.7% |
| transport + accommodation + dining + budget + tips | 395 | 17.6% |
| transport + dining + sightseeing + budget + tips | 192 | 8.5% |

**Markdown formatting:**

| Format | Count | % |
|--------|-------|---|
| headers + bold + numbered lists + tables | 1249 | 55.6% |
| headers + bold + tables | 999 | 44.4% |

Only 2 formatting patterns exist across all 2248 entries.

### 6.5 Tool Call Sequence Uniformity

Only **5 unique tool call sequences** exist, mapping 1:1 to the 5 query templates. The model will memorize 5 recipes rather than learning flexible tool orchestration.

---

## 7. Summary

### Strengths

1. **Zero broken entries**: All 2248 entries have valid plans, proper tool calls, and correct tool responses
2. **High POI grounding**: 59.8% mean reference rate with 0 entries at 0%
3. **Complete tool coverage**: weather and direction called in 100% of entries (matching system prompt requirements)
4. **No redundant calls**: Zero duplicate tool invocations
5. **Budget-aware**: 100% of plans address the user's budget
6. **Rich time specifics**: 70.4% of entries have 11+ specific time mentions

### Critical Concerns

1. **Template-generated data**: Only 5 query templates and 5 tool-call sequences. The dataset is 2248 parametric variations of 5 conversations, not 2248 unique conversations. The model learns to pattern-match template → recipe, not to reason about novel queries.

2. **Extremely narrow length distribution** (std=160 chars on mean=1882): Real travel plans should vary enormously by trip complexity. A 1-day business trip and a 5-day family vacation should not produce similar-length plans.

3. **Only 10 origin cities, ~25 destinations**: Geographic diversity is limited. The model may struggle with less common city pairs.

4. **No edge cases**: Zero entries with errors, unusual requests, clarification needs, or multi-turn negotiation. The model never learns to handle ambiguity or recover from tool failures.

5. **Reused tool call IDs** (1,331 IDs shared across entries): This is a data generation artifact that could confuse training if the model attends to call IDs.

6. **No variation in plan quality**: There are no LOW tier entries because the data was generated to be uniformly "good." The model doesn't learn to distinguish good from bad approaches.

7. **Formulaic response structure**: Only 2 markdown formatting patterns. Plans always follow the same section order. The model will produce rigid, template-like responses even for queries that deserve different treatment.

### Recommendations for Improvement

1. **Diversify query types**: Add open-ended queries ("plan something fun for this weekend"), multi-turn conversations, ambiguous requests requiring clarification, and edge cases (bad weather, cancelled flights, accessibility needs)
2. **Vary plan complexity**: Allow short plans for simple trips and long plans for complex ones
3. **Add error recovery**: Include entries where tool calls fail and the model adapts
4. **Expand geography**: Add more cities, international destinations, rural areas
5. **Break template uniformity**: Generate with more diverse prompt templates (>20) or use real user queries
6. **Fix tool call IDs**: Ensure unique IDs per entry to avoid training artifacts
7. **Add multi-turn interactions**: Include entries where the user asks follow-up questions or changes requirements mid-conversation
