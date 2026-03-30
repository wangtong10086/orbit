"""NAVWORLD problem generation, prompts, and tool schemas."""

import random
from datetime import datetime, timedelta

# ============================================================================
# System prompt
# ============================================================================

# EXACT COPY of eval's config.py SYSTEM_PROMPT — must stay in sync
SYSTEM_PROMPT = """你是一个专业的旅行规划助手，能够帮助用户规划旅行行程。

## 可用工具

你可以使用以下工具获取真实信息：

1. **poi_search(address, region)** - 搜索地点信息
   - address: 地点名称或关键词（如"西湖"、"火车站"）
   - region: 可选，城市名称用于缩小范围

2. **around_search(location, radius, keyword, region)** - 周边搜索
   - location: 中心点坐标（经度,纬度）
   - radius: 搜索半径（米，最大50000）
   - keyword: 搜索关键词
   - region: 可选，城市名称

3. **direction(origin, destination, mode, waypoints)** - 路线规划
   - origin: 起点坐标（经度,纬度）
   - destination: 终点坐标（经度,纬度）
   - mode: 出行方式（driving/walking/bicycling/transit）
   - waypoints: 可选，途经点列表

4. **weather(city)** - 天气查询
   - city: 城市名称

5. **search_flights(date, from_city, to_city)** - 航班搜索
   - date: 日期（YYYY-MM-DD格式）
   - from_city: 出发城市
   - to_city: 到达城市

6. **search_train_tickets(date, from_city, to_city, ...)** - 火车票搜索
   - date: 日期（YYYY-MM-DD格式）
   - from_city: 出发城市
   - to_city: 到达城市
   - 其他参数：城市代码和坐标（可从poi_search获取）

## 工作流程

1. **第一步**：调用 poi_search 搜索景点、酒店、餐厅等地点信息
2. **第二步**：调用 weather 查询目的地天气预报（**必须调用**）
3. **第三步**：调用 direction 规划景点之间的路线（**必须调用**）
4. **第四步**：如需要，调用 around_search 搜索周边设施
5. **最后**：根据所有工具返回的信息，提供详细的规划方案

## 重要要求

- **必须**调用多种工具获取完整信息，不能只使用 poi_search
- **必须**调用 weather 工具查询天气，这对旅行规划至关重要
- **必须**调用 direction 工具规划路线，提供具体的交通时间和距离
- 最终方案中的信息必须与工具返回的结果一致
- 不要编造工具没有返回的信息
- 在获取足够信息之前，不要急于给出最终规划
"""

# ============================================================================
# City data and constants
# ============================================================================

CITY_PAIRS_SHORT = [
    ("上海", "杭州"), ("北京", "天津"), ("广州", "深圳"),
    ("成都", "重庆"), ("南京", "苏州"), ("武汉", "长沙"),
    ("杭州", "宁波"), ("福州", "厦门"), ("昆明", "大理"),
]
CITY_PAIRS_MEDIUM = [
    ("北京", "上海"), ("上海", "南京"), ("广州", "长沙"),
    ("杭州", "厦门"), ("成都", "西安"), ("北京", "青岛"),
    ("上海", "武汉"), ("北京", "大连"), ("深圳", "厦门"),
]
CITY_PAIRS_LONG = [
    ("北京", "广州"), ("上海", "成都"), ("北京", "昆明"),
    ("上海", "西安"), ("北京", "三亚"), ("上海", "三亚"),
    ("北京", "成都"), ("广州", "西安"), ("北京", "哈尔滨"),
]
# Indirect routes — no direct flights/trains between these pairs
CITY_PAIRS_INDIRECT = [
    ("福州", "张家界"), ("昆明", "敦煌"), ("南宁", "丽江"),
    ("合肥", "大理"), ("贵阳", "青岛"), ("兰州", "厦门"),
    ("太原", "三亚"), ("南昌", "拉萨"), ("温州", "张家界"),
]
# Nearby pairs for half-day / short trips
CITY_PAIRS_NEARBY = [
    ("杭州", "乌镇"), ("成都", "乐山"), ("长沙", "凤凰"),
    ("南京", "镇江"), ("苏州", "周庄"), ("广州", "佛山"),
    ("西安", "华山"), ("武汉", "黄鹤楼"), ("重庆", "大足"),
]

MAJOR_CITIES = [
    "北京", "上海", "广州", "深圳", "杭州", "成都", "西安", "重庆",
    "南京", "武汉", "长沙", "苏州", "天津", "青岛", "厦门", "大连",
    "昆明", "三亚", "桂林", "丽江", "张家界", "黄山", "洛阳",
    "大同", "荔波", "凤凰", "乌镇", "婺源", "阳朔", "平遥",
    "敦煌", "泉州", "开封", "济南", "绍兴", "镇江", "太原",
    "哈尔滨", "贵阳", "兰州", "合肥", "南昌", "温州",
]

INTERESTS = [
    "natural scenery", "culture & history", "food exploration", "shopping", "leisure vacation",
    "photography", "family fun", "outdoor sports", "folk customs", "museums",
]

INTERESTS_ZH = [
    "自然风光", "历史文化", "美食探索", "购物休闲", "休闲度假",
    "摄影打卡", "亲子游乐", "户外运动", "民俗体验", "博物馆",
]

PREFERENCES = ["舒适优先", "经济优先", "速度优先"]

# Original 5 types + 8 Phase 1 diversity types
PROBLEM_TYPES = ["intercity", "multiday", "hybrid", "food_tour", "business"]
PHASE1_TYPES = [
    "weekend_escape",   # A1: open-ended, no fixed destination
    "half_day",         # E2: short sequence (3-5 tools)
    "budget_trip",      # E1: ultra-budget
    "no_direct",        # C1: transport fallback
    "bad_weather",      # C2: weather-conditional branching
    "photo_route",      # D4: multi-leg direction calls
    "mid_change",       # B1: multi-turn, user changes mind
    "empty_result",     # C3: handle sparse POI results
    "single_poi",       # Eval type: deep-dive one POI area, no transport
    "family_study",     # Eval type: family educational trip with kids
]
ALL_PROBLEM_TYPES = PROBLEM_TYPES + PHASE1_TYPES

# POI focus categories for single_poi type (matching eval's landmarks)
SINGLE_POI_TYPES = [
    "博物馆", "古镇", "古城墙", "寺庙", "园林", "湖泊公园",
    "历史街区", "名山", "主题乐园", "美术馆", "科技馆",
]

# Study themes for family_study type (matching eval's STUDY_THEMES)
STUDY_THEMES = [
    "科技馆探索", "博物馆研学", "非遗手工体验", "自然生态研学",
    "天文观测", "海洋世界探索", "历史文化研学", "农耕体验",
]


def generate_problem(task_id: int, problem_type: str = None) -> dict:
    """Generate a travel planning problem deterministically.

    If problem_type is given, use it directly (for Phase 1 diversity generation).
    Otherwise fall back to round-robin over the original 5 types.
    """
    rng = random.Random(task_id)
    ptype = problem_type or PROBLEM_TYPES[task_id % len(PROBLEM_TYPES)]

    # Pick cities based on problem type
    if ptype == "no_direct":
        origin, dest = rng.choice(CITY_PAIRS_INDIRECT)
    elif ptype == "half_day":
        origin, dest = rng.choice(CITY_PAIRS_NEARBY)
    elif ptype == "weekend_escape":
        # Open-ended: origin only, destination decided by model
        origin = rng.choice(MAJOR_CITIES)
        dest = None  # model must suggest
    elif ptype == "empty_result":
        # Small/rural destinations with sparse POI data
        rural = [("贵阳", "荔波"), ("长沙", "凤凰"), ("桂林", "阳朔"),
                 ("太原", "平遥"), ("西安", "华山"), ("昆明", "大理")]
        origin, dest = rng.choice(rural)
    elif ptype in ("intercity", "hybrid", "business"):
        pairs = CITY_PAIRS_SHORT + CITY_PAIRS_MEDIUM + CITY_PAIRS_LONG
        origin, dest = rng.choice(pairs)
    else:
        pairs = CITY_PAIRS_SHORT + CITY_PAIRS_MEDIUM
        origin, dest = rng.choice(pairs)

    # Date: 7-60 days from now
    travel_date = (datetime.now() + timedelta(days=rng.randint(7, 60))).strftime("%Y-%m-%d")

    # Duration depends on type
    if ptype == "half_day":
        num_days = 0  # half-day trip
    elif ptype == "weekend_escape":
        num_days = 2
    elif ptype in ("multiday", "hybrid", "food_tour", "photo_route", "bad_weather"):
        num_days = rng.randint(2, 5)
    else:
        num_days = rng.randint(1, 3)

    # Budget depends on type
    if ptype == "budget_trip":
        budget = rng.randint(200, 800)
    elif ptype == "half_day":
        budget = rng.randint(100, 500)
    else:
        budget = rng.randint(500, 5000)

    interests = rng.sample(INTERESTS_ZH, rng.randint(1, 3))
    pref = rng.choice(PREFERENCES) if ptype in ("intercity", "business") else None

    problem = {
        "task_id": task_id,
        "type": ptype,
        "origin": origin,
        "date": travel_date,
        "num_days": num_days,
        "budget": budget,
        "interests": interests,
        "preference": pref,
    }
    if dest is not None:
        problem["destination"] = dest

    # For mid_change: also generate an alternative destination
    if ptype == "mid_change":
        alt_pairs = CITY_PAIRS_SHORT + CITY_PAIRS_MEDIUM
        alt_origin, alt_dest = rng.choice(alt_pairs)
        # Ensure alt_dest != dest
        while alt_dest == dest:
            alt_origin, alt_dest = rng.choice(alt_pairs)
        problem["alt_destination"] = alt_dest

    # single_poi: no origin, single day, focus on one POI category
    if ptype == "single_poi":
        problem["origin"] = ""
        problem["num_days"] = 1
        problem["budget"] = rng.randint(100, 600)
        problem["poi_focus"] = rng.choice(SINGLE_POI_TYPES)
        problem["interests"] = [problem["poi_focus"], rng.choice(["摄影打卡", "深度体验", "历史文化", "自然风光"])]

    # family_study: no origin, multi-day, family group, educational theme
    if ptype == "family_study":
        problem["origin"] = ""
        problem["num_days"] = rng.randint(3, 5)
        problem["budget"] = rng.randint(2000, 8000)
        problem["group_size"] = rng.randint(3, 5)
        problem["study_theme"] = rng.choice(STUDY_THEMES)
        problem["interests"] = [problem["study_theme"], "亲子游乐", rng.choice(INTERESTS_ZH)]

    return problem


def problem_to_prompt(p: dict) -> str:
    """Convert problem dict to user prompt string."""
    ptype = p["type"]
    # === All 7 eval types: Chinese prompts copied from eval's problem_generator.py ===
    if ptype == "intercity":
        parts = [f"我计划从{p['origin']}去{p['destination']}"]
        parts.append(f"出发日期是{p['date']}")
        parts.append(f"预算{p['budget']}元/人")
        if p.get("preference") and p["preference"] != "无特殊要求":
            parts.append(f"偏好{p['preference']}")
        prompt = "，".join(parts) + "。"
        prompt += "\n\n请帮我：\n"
        prompt += "1. 查询所有可选的航班和火车车次（列出班次号、时间、价格）\n"
        prompt += "2. 至少对比3种出行方案，分析各自优劣（时间、价格、舒适度）\n"
        prompt += "3. 推荐最佳方案并详细说明理由\n"
        prompt += "4. 到达后的景点推荐和简要安排建议"
        return prompt
    elif ptype == "multiday":
        prompt = f"请为我规划一次{p['destination']}{p['num_days']}日游"
        prompt += f"，出发日期：{p['date']}，总预算：{p['budget']}元。"
        if p.get("interests"):
            prompt += f"\n\n兴趣偏好：{', '.join(p['interests'])}"
        prompt += "\n\n请提供详细的每日行程安排，包括：\n"
        prompt += "1. 每天的景点安排和路线规划（每天至少2-3个景点，标注门票价格）\n"
        prompt += "2. 每天的餐饮推荐（具体餐厅名称和人均消费）\n"
        prompt += "3. 住宿建议（具体酒店名称、价格区间和位置优势）\n"
        prompt += "4. 各景点间的交通方式、距离和预计时间\n"
        prompt += "5. 每日花费明细和总预算分配"
        return prompt
    elif ptype == "hybrid":
        prompt = f"我计划从{p['origin']}出发去{p['destination']}玩{p['num_days']}天。\n\n"
        prompt += f"基本信息：\n"
        prompt += f"- 出发日期：{p['date']}\n"
        prompt += f"- 总预算：{p['budget']}元\n"
        if p.get("preference") and p["preference"] != "无特殊要求":
            prompt += f"- 交通偏好：{p['preference']}\n"
        if p.get("interests"):
            prompt += f"\n兴趣偏好：{', '.join(p['interests'])}"
        prompt += "\n\n请帮我完成完整的旅行规划：\n"
        prompt += "1. 往返交通方案（至少对比2种方案，列出航班号/车次、时间、价格）\n"
        prompt += "2. 每日详细行程安排（每天至少2-3个景点，含门票和交通）\n"
        prompt += "3. 每天的餐饮推荐（具体餐厅名称和人均价格）和住宿建议\n"
        prompt += "4. 完整预算明细（交通、住宿、餐饮、门票分项合计）"
        return prompt
    elif ptype == "food_tour":
        prompt = f"我想在{p['destination']}来一次美食之旅"
        if p["num_days"] > 1:
            prompt += f"，计划{p['num_days']}天"
        prompt += "。\n\n"
        prompt += f"基本信息：\n"
        prompt += f"- 日期：{p['date']}\n"
        if p.get("budget"):
            prompt += f"- 餐饮预算：{p['budget']}元\n"
        prompt += "\n请帮我规划：\n"
        prompt += "1. 至少推荐6-8家必吃的特色餐厅/店铺（含具体店名和招牌菜）\n"
        prompt += "2. 按区域或时间段规划美食路线（标注每家店的区域位置）\n"
        prompt += "3. 各店铺之间的交通方式、步行距离和所需时间\n"
        prompt += "4. 每家店的人均消费和总预算分配\n"
        prompt += "5. 用餐时间建议和排队预估"
        return prompt
    elif ptype == "business":
        purpose = "商务出行"
        prompt = f"我因{purpose}需要从{p['origin']}前往{p['destination']}"
        if p["num_days"] > 1:
            prompt += f"，预计{p['num_days']}天"
        prompt += "。\n\n"
        prompt += f"基本信息：\n"
        prompt += f"- 出发日期：{p['date']}\n"
        if p.get("budget"):
            prompt += f"- 差旅预算：{p['budget']}元\n"
        if p.get("preference"):
            prompt += f"- 交通偏好：{p['preference']}\n"
        prompt += "\n请帮我规划：\n"
        prompt += "1. 至少对比2-3种交通方案（列出航班号/车次、时间、价格）\n"
        prompt += "2. 推荐2-3家商务区附近的酒店（含价格、距离会场/客户距离）\n"
        prompt += "3. 每天的餐饮安排（具体餐厅名称和商务宴请选择）\n"
        prompt += "4. 详细差旅费用预估（交通+住宿+餐饮分项明细）"
        return prompt

    # === Phase 1 diversity types (Chinese prompts) ===

    elif ptype == "weekend_escape":
        prompt = f"这个周末想出去玩，从{p['origin']}出发，预算{p['budget']}块，两天一夜，去哪好？帮我安排一下。\n"
        prompt += f"出发日期：{p['date']}\n"
        prompt += f"兴趣偏好：{', '.join(p['interests'])}\n"
        prompt += "不限目的地，帮我推荐一个合适的地方，然后做详细规划。"
        return prompt

    elif ptype == "half_day":
        dest = p.get('destination', p['origin'])
        prompt = f"我在{dest}转机/中转，有5个小时空闲，想在市区逛逛。\n"
        prompt += f"日期：{p['date']}，预算{p['budget']}元以内。\n"
        prompt += "请推荐几个值得去的地方，帮我规划一下路线，包括怎么去、要多久、附近有什么吃的。"
        return prompt

    elif ptype == "budget_trip":
        prompt = f"学生党穷游，从{p['origin']}去{p['destination']}玩{p['num_days']}天，"
        prompt += f"总共只有{p['budget']}块（含车票），怎么玩？\n"
        prompt += f"出发日期：{p['date']}\n"
        prompt += "请帮我找最便宜的交通方式、免费或便宜的景点、实惠的吃饭地方，尽量步行或坐公交。"
        return prompt

    elif ptype == "no_direct":
        prompt = f"我从{p['origin']}想去{p['destination']}，{p['date']}出发，{p['num_days']}天。\n"
        prompt += f"预算{p['budget']}元。\n"
        prompt += "帮我查查怎么去最方便，如果没有直达的航班或火车，帮我找中转方案。\n"
        prompt += "到了之后帮我安排景点和住宿。"
        return prompt

    elif ptype == "bad_weather":
        prompt = f"下周去{p['destination']}玩{p['num_days']}天，从{p['origin']}出发。\n"
        prompt += f"出发日期：{p['date']}，预算{p['budget']}元。\n"
        prompt += "帮我规划行程，先查一下天气。如果下雨的话，有什么室内备选方案？\n"
        prompt += "请同时准备晴天方案和雨天方案。"
        return prompt

    elif ptype == "photo_route":
        prompt = f"我是摄影爱好者，想去{p['destination']}拍{p['num_days']}天。\n"
        prompt += f"从{p['origin']}出发，日期{p['date']}，预算{p['budget']}元。\n"
        prompt += "帮我安排拍摄路线，要包括日出日落机位和夜景拍摄点。\n"
        prompt += "请先查天气（云量很重要），然后帮我找观景台、拍摄点，规划每段路线的距离和时间。"
        return prompt

    elif ptype == "mid_change":
        dest = p.get('destination', '三亚')
        prompt = f"帮我查一下{p['origin']}到{dest}的机票和酒店，{p['date']}出发，{p['num_days']}天。\n"
        prompt += f"预算{p['budget']}元，兴趣：{', '.join(p['interests'])}。"
        return prompt

    elif ptype == "empty_result":
        dest = p.get('destination', '荔波')
        prompt = f"想去{dest}玩{p['num_days']}天，从{p['origin']}出发。\n"
        prompt += f"日期：{p['date']}，预算{p['budget']}元。\n"
        prompt += f"帮我查查怎么去，附近有住的地方吗？有什么好玩的景点？\n"
        prompt += "如果搜不到太多信息，帮我找找附近的替代方案。"
        return prompt

    elif ptype == "single_poi":
        dest = p.get("destination", "杭州")
        poi = p.get("poi_focus", "博物馆")
        prompt = f"我想在{dest}深度游览{poi}及其周边区域，{p['date']}出发，一天时间。\n"
        prompt += f"预算{p['budget']}元。\n\n"
        prompt += "请帮我：\n"
        prompt += f"1. 搜索{dest}最值得去的{poi}及周边4-5个景点/餐厅\n"
        prompt += "2. 规划最佳游览路线（上午和下午分段）\n"
        prompt += "3. 提供各景点之间的交通方式、距离和时间\n"
        prompt += "4. 门票价格、开放时间\n"
        prompt += "5. 总费用预算明细（交通XX元+餐饮XX元+门票XX元=总计XX元）\n"
        prompt += "6. 天气情况与穿衣建议\n"
        prompt += "7. 实用出行建议（如最佳游览时段、预约方式、携带物品、注意事项等）"
        return prompt

    elif ptype == "family_study":
        dest = p.get("destination", "北京")
        theme = p.get("study_theme", "博物馆研学")
        group_size = p.get("group_size", 4)
        prompt = f"我们一家{group_size}口想去{dest}进行一次{theme}之旅，计划{p['num_days']}天。\n"
        prompt += f"出发日期：{p['date']}，总预算{p['budget']}元。\n\n"
        prompt += "请帮我：\n"
        prompt += "1. 每天安排1个教育类景点 + 1个休闲娱乐活动（适合小朋友）\n"
        prompt += "2. 每天详细行程（上午/下午），包括景点间交通方式和时间\n"
        prompt += "3. 推荐适合带小孩的餐厅和亲子房酒店\n"
        prompt += "4. 门票价格（注明儿童票/家庭票优惠）\n"
        prompt += "5. 总预算分日明细（交通XX元+住宿XX元+餐饮XX元+门票XX元=总计XX元）\n"
        prompt += "6. 天气情况与穿衣建议\n"
        prompt += "7. 实用出行建议（预约方式、携带物品、注意事项等）"
        return prompt

    return f"请帮我规划一次去{p.get('destination', '杭州')}的旅行。"


# ============================================================================
# Tool schema (OpenAI function calling format)
# ============================================================================

# EXACT COPY of eval's config.py TOOLS_SCHEMA — must stay in sync
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "poi_search",
            "description": "搜索地点信息（景点、酒店、餐厅等POI）。返回地点的名称、地址、坐标等信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "搜索关键词或地址，如'西湖'、'北京火车站'、'餐厅'"
                    },
                    "region": {
                        "type": "string",
                        "description": "城市名称，用于缩小搜索范围，如'杭州'、'北京'"
                    }
                },
                "required": ["address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "around_search",
            "description": "周边搜索。在指定中心点和半径范围内搜索地点。",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "中心点坐标，格式为'经度,纬度'，如'120.15,30.28'"
                    },
                    "radius": {
                        "type": "integer",
                        "description": "搜索半径（米），范围0-50000"
                    },
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词，如'餐厅'、'酒店'"
                    },
                    "region": {
                        "type": "string",
                        "description": "城市名称"
                    }
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "direction",
            "description": "路线规划。计算两点之间的路线、距离和时间。",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {
                        "type": "string",
                        "description": "起点坐标，格式为'经度,纬度'"
                    },
                    "destination": {
                        "type": "string",
                        "description": "终点坐标，格式为'经度,纬度'"
                    },
                    "mode": {
                        "type": "string",
                        "description": "出行方式：driving（驾车）、walking（步行）、bicycling（骑行）、transit（公交）",
                        "enum": ["driving", "walking", "bicycling", "transit"]
                    },
                    "waypoints": {
                        "type": "string",
                        "description": "途经点坐标列表，用分号分隔"
                    }
                },
                "required": ["origin", "destination"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "weather",
            "description": "天气查询。获取指定城市的天气预报。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，如'杭州'、'北京'"
                    }
                },
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_flights",
            "description": "航班搜索。查询两个城市之间的航班信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "出发日期，格式YYYY-MM-DD"
                    },
                    "from_city": {
                        "type": "string",
                        "description": "出发城市中文名"
                    },
                    "to_city": {
                        "type": "string",
                        "description": "到达城市中文名"
                    }
                },
                "required": ["date", "from_city", "to_city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_train_tickets",
            "description": "火车票搜索。查询两个城市之间的火车票信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "出发日期，格式YYYY-MM-DD"
                    },
                    "from_city": {
                        "type": "string",
                        "description": "出发城市中文名"
                    },
                    "to_city": {
                        "type": "string",
                        "description": "到达城市中文名"
                    },
                    "from_city_adcode": {
                        "type": "string",
                        "description": "出发城市行政区划代码"
                    },
                    "to_city_adcode": {
                        "type": "string",
                        "description": "到达城市行政区划代码"
                    },
                    "from_lat": {
                        "type": "string",
                        "description": "出发城市纬度"
                    },
                    "from_lon": {
                        "type": "string",
                        "description": "出发城市经度"
                    },
                    "to_lat": {
                        "type": "string",
                        "description": "到达城市纬度"
                    },
                    "to_lon": {
                        "type": "string",
                        "description": "到达城市经度"
                    }
                },
                "required": ["date", "from_city", "to_city"]
            }
        }
    },
]