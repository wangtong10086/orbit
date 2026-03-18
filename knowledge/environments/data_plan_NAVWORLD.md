# NAVWORLD 数据方案

> 最后更新: 2026-03-18 | 优先级: P0 (GM 杠杆最大) | v1 状态: 训练中

## 现状

| 指标 | 值 |
|------|-----|
| canonical 条数 | 2,248 |
| v1 用量 | 2,248 (全量) |
| 历史分数 | 5.7 (v11), 28% non-zero |
| 竞品最高 | 24.56 (AnastasiaFantasy) |
| GM 贡献潜力 | 5.7→18 = **+6.4 GM** (全环境最高) |
| 数据格式 | OpenAI function calling (tool_calls + tool role) |
| 语言 | 100% 中文 |

## 评估格式详解 (源码: affinetes)

### 消息结构
```json
[
  {"role": "system", "content": "你是一个旅行规划助手..."},
  {"role": "user", "content": "帮我规划从北京到上海的三日游..."},
  {"role": "assistant", "content": null, "tool_calls": [
    {"id": "call_abc123", "type": "function", "function": {
      "name": "poi_search", "arguments": "{\"address\":\"上海外滩\",\"region\":\"上海\"}"
    }}
  ]},
  {"role": "tool", "content": "{\"pois\":[...]}", "tool_call_id": "call_abc123"},
  {"role": "assistant", "content": "根据搜索结果，我为您推荐...（最终方案 ≥200 字）"}
]
```

### 工具 Schema (6 个)

| 工具 | 参数 | 返回 | 必要性 |
|------|------|------|--------|
| **poi_search** | address (str), region (str, optional) | POI 列表 (名称/坐标/类型) | **必须** |
| **around_search** | location ("lng,lat"), radius (int, 米), keyword (str) | 附近 POI | 推荐 |
| **direction** | origin (坐标), destination (坐标), mode (driving\|walking\|bicycling\|transit) | 距离/时间/策略 | **必须** |
| **weather** | city (str) | 天气预报 | **必须** |
| **search_flights** | date (YYYY-MM-DD), from_city (str), to_city (str) | 航班列表 | 按场景 |
| **search_train_tickets** | date (YYYY-MM-DD), from_city (str), to_city (str) | 车次列表 | 按场景 |

### 评分算法 (50 + 50)

**代码评分 (50 分)**:
- 信息一致性: 最终方案中的 POI/交通信息是否与工具返回匹配
- 完整性: 是否覆盖所有用户需求 (景点/交通/天气/住宿/餐饮)
- 格式检查: `format_valid` 要求最终 assistant 消息 ≥100 字符
- POI grounding: 工具返回的具体地点名称必须出现在最终方案中
- 模板检测惩罚: 缺少推理连接词 (因为|由于|所以|因此|建议|推荐|考虑到|综合|权衡|对比|相比|优先|适合) 会降分

**LLM 语义评分 (50 分)**:
- 旅行方案的自然度、合理性、完整性
- 推荐质量 (是否真正有用, 非模板化)

### 关键部署要求
1. **训练**: `tokenizer.apply_chat_template(messages, tools=tools)` → Qwen3 原生格式 (`<tool_call>JSON</tool_call>`)
2. **推理**: sglang 必须加 `--tool-call-parser qwen25`
3. **缺任一则 0 分** (历史教训: v3-v7 全是 0)

### Task ID 与场景类型
- `problem = generate_problem(task_id)`, rng = Random(task_id)
- 场景类型 = `PROBLEM_TYPES[task_id % len]`:
  - intercity: 城际交通比较 (飞机 vs 火车)
  - multiday: 多日行程规划
  - hybrid: 跨城 + 本地活动
  - food_tour: 美食主题行程
  - business: 商务出行

### Eval 参数
- Timeout: 7200s, Temperature: 0.7, Memory: 2GB, Concurrency: 4
- Docker image: qqr:eval
- 环境变量: AMAP_MAPS_API_KEY (必须)

## 数据质量审计结果

结构性指标全部通过:
| 指标 | 结果 | 详情 |
|------|------|------|
| 工具多样性 ≥3 种 | 100% (2248/2248) | 5 种核心工具 100% 覆盖 |
| 最终方案 ≥800 字 | 100% | min=1413, median=1870, max=2611 |
| 消息轮数 | 13-16 轮 (mean=14.6) | 非常一致 |
| 总长度 | 6003-9457 chars | 全部 fit 在 seq=4096 |
| search_flights 覆盖 | 100% | 全部覆盖 (v11+ 重新审计) |
| direction 工具覆盖 | 100% | v11 重新生成后全部覆盖 |

**关键发现**: 结构完美, 但所有 2,248 条 score=1.0 (自动标注)。SFT 瓶颈已确认 (+240% 数据仅 +12% 提升), 问题在**语义质量**而非格式/数量。

### POI Grounding 分析 (2026-03-18 深度审计)
抽样 5 条检查"工具返回的 POI 名称是否出现在最终方案中":
- 最佳: 92% (14个POI中13个在方案中)
- 最差: 50% (20个POI中10个在方案中)
- 中位: ~75%

**假说**: 低 grounding 率可能是代码评分 (50分) 丢分的主因 — 方案中未引用工具返回的具体地点名称。
**v2a 优化方向**: 过滤保留 grounding ≥80% 的条目，或在合成时要求模型引用工具返回的所有 POI。

## 瓶颈分析

| 瓶颈 | 影响 | 证据 | 解法 |
|------|------|------|------|
| SFT 天花板 | 数据量不再有效 | +240% 数据仅 +12% 提升 (v10→v11) | DPO (v3) |
| 语义质量未知 | 不知丢分在哪 50 分 | 全部 score=1.0 | 用代码评分逻辑筛选 |
| 评分解构不明 | 无法针对性优化 | 50 代码 + 50 LLM, 占比不清 | v1 结果分析 |
| 合成偏差 | qwen3-max 可能有系统性问题 | 全部合成数据 | 质量过滤 + 多样化场景 |
| 推理连接词 | 模板化方案被惩罚 | 评分逻辑检查 ≥3 个连接词 | 确保方案含推理过程 |

## 数据行动方案

### v1: 维持现有 (当前阶段 — 训练中)
- **不做修改**: 2,248 条全部用于 v1 baseline
- 目的: 建立基线分数, 确认实际丢分点 (代码评分 vs LLM 评分)
- 预期: NAVWORLD ~5-8 分 (基于 v11 历史)

### v2: 质量过滤 + 场景优化 (等 v1 结果)
| 任务 | 方法 | 目标 | 优先级 |
|------|------|------|--------|
| 代码评分筛选 | 用 eval 代码评分逻辑对 2248 条打分 | 保留 ~1200-1500 高质量 | P1 |
| 场景覆盖分析 | 按 5 种场景类型统计分布 | 确保均匀覆盖 | P1 |
| 推理连接词检查 | 验证最终方案含 ≥3 个推理词 | 避免模板惩罚 | P2 |
| POI grounding 检查 | 验证方案中 POI 名与工具返回一致 | 提升代码评分 | P2 |
| 复杂场景新增 | 多日行程、跨城、预算约束 | 扩展多样性 | P3 |
| 错误恢复场景 | 工具返回空结果 → 重试 | 提升鲁棒性 | P3 |

### v3: DPO 突破 (SFT 天花板确认后)
- 241 对偏好对已就绪
- DPO 直接在 tool-calling 轨迹上做偏好学习
- 目标: 突破 SFT 天花板 5.7→20+ 分
- **这是全项目 GM ROI 最高的行动** (5.7→18 = +6.4 GM)

## 数据质量检查清单

- [x] `datasets.load_dataset('json', data_files=...)` 成功
- [x] Schema: `{"messages": [...], "env": "NAVWORLD", "score": float}`
- [x] 最后一条消息 role=assistant
- [x] 工具调用使用 OpenAI function calling 格式 (tool_calls 字段)
- [x] 每条数据包含 poi_search + weather + direction
- [x] 最终方案 ≥200 字符 (实际 ≥1413)
- [x] 全部中文
- [x] 工具多样性 ≥3 种
- [ ] POI grounding 验证 (v2)
- [ ] 推理连接词 ≥3 (v2)
- [ ] 场景类型覆盖均衡 (v2)

## 准备文件

| 文件 | 位置 | 条数 | 状态 |
|------|------|------|------|
| canonical | `data/canonical/navworld.jsonl` | 2,248 | claudeuser-owned, v1 使用中 |
| DPO 数据 | — | 241 对 | 可用 (v3) |
| 生成脚本 | `forge/data/navworld_gen.py` | — | qwen3-max 合成 |
| 工具 schema | `forge/data/navworld_prompts.py` | — | 6 个工具定义 |
