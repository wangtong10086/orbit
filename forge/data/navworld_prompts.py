"""NAVWORLD problem generation, prompts, and tool schemas."""

import random
from datetime import datetime, timedelta

# ============================================================================
# System prompt
# ============================================================================

SYSTEM_PROMPT = """You are a professional travel planning assistant that helps users plan their trips.

## Available Tools

You can use the following tools to gather real information:

1. **poi_search(address, region)** - Search for location information
   - address: Place name or keyword (e.g. "West Lake", "train station")
   - region: Optional, city name to narrow the search

2. **around_search(location, radius, keyword, region)** - Nearby search
   - location: Center point coordinates (longitude,latitude)
   - radius: Search radius in meters (max 50000)
   - keyword: Search keyword
   - region: Optional, city name

3. **direction(origin, destination, mode, waypoints)** - Route planning
   - origin: Start point coordinates (longitude,latitude)
   - destination: End point coordinates (longitude,latitude)
   - mode: Travel mode (driving/walking/bicycling/transit)
   - waypoints: Optional, list of waypoints

4. **weather(city)** - Weather query
   - city: City name

5. **search_flights(date, from_city, to_city)** - Flight search
   - date: Date (YYYY-MM-DD format)
   - from_city: Departure city
   - to_city: Arrival city

6. **search_train_tickets(date, from_city, to_city, ...)** - Train ticket search
   - date: Date (YYYY-MM-DD format)
   - from_city: Departure city
   - to_city: Arrival city
   - Other parameters: city codes and coordinates (obtainable from poi_search)

## Workflow

1. **Step 1**: Call poi_search to search for attractions, hotels, restaurants, etc.
2. **Step 2**: Call weather to query destination weather forecast (**required**)
3. **Step 3**: Call direction to plan routes between attractions (**required**)
4. **Step 4**: If needed, call around_search to search for nearby facilities
5. **Finally**: Based on all tool-returned information, provide a detailed plan

## Important Requirements

- **Must** call multiple tools to gather complete information; do not use only poi_search
- **Must** call the weather tool to query weather, which is critical for travel planning
- **Must** call the direction tool to plan routes, providing specific travel times and distances
- Information in the final plan must be consistent with tool-returned results
- Do not fabricate information not returned by tools
- Do not rush to provide a final plan before gathering sufficient information
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

PREFERENCES = ["comfort first", "budget first", "speed first"]

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
]
ALL_PROBLEM_TYPES = PROBLEM_TYPES + PHASE1_TYPES


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

    return problem


def problem_to_prompt(p: dict) -> str:
    """Convert problem dict to user prompt string."""
    ptype = p["type"]
    if ptype == "intercity":
        parts = [f"I plan to travel from {p['origin']} to {p['destination']}"]
        parts.append(f"departure date is {p['date']}")
        parts.append(f"budget {p['budget']} CNY/person")
        if p.get("preference"):
            parts.append(f"preference: {p['preference']}")
        prompt = ", ".join(parts) + "."
        prompt += "\n\nPlease help me:\n"
        prompt += "1. Look up all available flights and trains (list flight/train numbers, times, prices)\n"
        prompt += "2. Compare at least 3 travel options, analyzing pros and cons (time, price, comfort)\n"
        prompt += "3. Recommend the best option with detailed reasoning\n"
        prompt += "4. Attraction recommendations and brief itinerary suggestions upon arrival"
        return prompt
    elif ptype == "multiday":
        prompt = f"I plan to travel from {p['origin']} to {p['destination']} for a {p['num_days']}-day trip"
        prompt += f", departure date: {p['date']}, total budget: {p['budget']} CNY."
        prompt += f"\n\nInterests: {', '.join(p['interests'])}"
        prompt += "\n\nPlease provide a detailed plan including:\n"
        prompt += "1. Round-trip transportation options (flights vs high-speed rail comparison)\n"
        prompt += "2. Daily attraction schedule and route planning\n"
        prompt += "3. Daily dining recommendations (specific restaurant names and per-person cost)\n"
        prompt += "4. Accommodation suggestions (specific hotel names, price range)\n"
        prompt += "5. Transportation modes, distances, and estimated times between attractions\n"
        prompt += "6. Daily expense breakdown and total budget allocation"
        return prompt
    elif ptype == "hybrid":
        prompt = f"I plan to travel from {p['origin']} to {p['destination']} for {p['num_days']} days.\n\n"
        prompt += f"Basic information:\n"
        prompt += f"- Departure date: {p['date']}\n"
        prompt += f"- Total budget: {p['budget']} CNY\n"
        if p.get("preference"):
            prompt += f"- Transportation preference: {p['preference']}\n"
        prompt += f"\nInterests: {', '.join(p['interests'])}"
        prompt += "\n\nPlease help me complete a full travel plan:\n"
        prompt += "1. Round-trip transportation options (compare at least 2 options)\n"
        prompt += "2. Detailed daily itinerary\n"
        prompt += "3. Dining and accommodation recommendations\n"
        prompt += "4. Complete budget breakdown"
        return prompt
    elif ptype == "food_tour":
        prompt = f"I'm departing from {p['origin']} and want to go to {p['destination']} for a {p['num_days']}-day food tour.\n"
        prompt += f"Departure date: {p['date']}, total budget: {p['budget']} CNY.\n"
        prompt += "\nPlease provide:\n"
        prompt += "1. Round-trip transportation options (train schedule comparison)\n"
        prompt += "2. Daily dining plan (breakfast, lunch, dinner + snacks, specific restaurant names and per-person cost)\n"
        prompt += "3. Transportation routes and times between restaurants\n"
        prompt += "4. Attractions to visit along the way\n"
        prompt += "5. Local weather and clothing suggestions"
        return prompt
    elif ptype == "business":
        prompt = f"I need to travel from {p['origin']} to {p['destination']} for a business trip.\n"
        prompt += f"Departure date: {p['date']}, budget {p['budget']} CNY/person"
        if p.get("preference"):
            prompt += f", {p['preference']}"
        prompt += ".\n\nPlease help me:\n"
        prompt += "1. Look up flights and high-speed rail, compare prices and times\n"
        prompt += "2. Recommend downtown business hotels\n"
        prompt += "3. Provide local weather information\n"
        prompt += "4. Recommend dining and leisure venues for after work"
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

    return f"请帮我规划一次去{p.get('destination', '杭州')}的旅行。"


# ============================================================================
# Tool schema (OpenAI function calling format)
# ============================================================================

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "poi_search",
            "description": "Search for location information (attractions, hotels, restaurants, and other POIs).",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "Search keyword or address"},
                    "region": {"type": "string", "description": "City name"},
                },
                "required": ["address"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "around_search",
            "description": "Nearby search. Search for locations within a specified center point and radius.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "Center point coordinates, format: 'longitude,latitude'"},
                    "radius": {"type": "integer", "description": "Search radius in meters"},
                    "keyword": {"type": "string", "description": "Search keyword"},
                    "region": {"type": "string", "description": "City name"},
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "direction",
            "description": "Route planning. Calculate route, distance, and time between two points.",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "Origin coordinates, format: 'longitude,latitude'"},
                    "destination": {"type": "string", "description": "Destination coordinates, format: 'longitude,latitude'"},
                    "mode": {"type": "string", "description": "Travel mode", "enum": ["driving", "walking", "transit"]},
                },
                "required": ["origin", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "weather",
            "description": "Weather query. Get weather forecast for a specified city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"},
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_flights",
            "description": "Flight search. Query flight information between two cities.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Departure date, format YYYY-MM-DD"},
                    "from_city": {"type": "string", "description": "Departure city name (Chinese)"},
                    "to_city": {"type": "string", "description": "Arrival city name (Chinese)"},
                },
                "required": ["date", "from_city", "to_city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_train_tickets",
            "description": "Train ticket search. Query train ticket information between two cities.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Departure date, format YYYY-MM-DD"},
                    "from_city": {"type": "string", "description": "Departure city name (Chinese)"},
                    "to_city": {"type": "string", "description": "Arrival city name (Chinese)"},
                },
                "required": ["date", "from_city", "to_city"],
            },
        },
    },
]