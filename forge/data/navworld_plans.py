"""NAVWORLD tool call plans — defines which tools to call per problem type.

Each plan is a list of steps. Each step is either:
- A list of (tool_name, args_fn) tuples for parallel tool calls
- A string naming a dynamic step resolved at generation time in navworld_gen.py
"""

# Original 5 types
TOOL_PLANS = {
    "intercity": [
        [("search_flights", lambda p: {"date": p["date"], "from_city": p["origin"], "to_city": p["destination"]}),
         ("search_train_tickets", lambda p: {"date": p["date"], "from_city": p["origin"], "to_city": p["destination"]})],
        [("poi_search", lambda p: {"address": "景点", "region": p["destination"]}),
         ("weather", lambda p: {"city": p["destination"]})],
        "direction_step",
        "around_step",
    ],
    "multiday": [
        [("poi_search", lambda p: {"address": "景点", "region": p["destination"]}),
         ("weather", lambda p: {"city": p["destination"]})],
        [("poi_search", lambda p: {"address": "酒店", "region": p["destination"]}),
         ("poi_search", lambda p: {"address": "餐厅", "region": p["destination"]})],
        # Only search transport if origin is set and different from destination
        "transport_if_origin",
        "direction_step",
        "around_step",
    ],
    "hybrid": [
        [("search_flights", lambda p: {"date": p["date"], "from_city": p["origin"], "to_city": p["destination"]}),
         ("search_train_tickets", lambda p: {"date": p["date"], "from_city": p["origin"], "to_city": p["destination"]})],
        [("poi_search", lambda p: {"address": "景点", "region": p["destination"]}),
         ("weather", lambda p: {"city": p["destination"]})],
        [("poi_search", lambda p: {"address": "酒店", "region": p["destination"]}),
         ("poi_search", lambda p: {"address": "餐厅", "region": p["destination"]})],
        "direction_step",
        "around_step",
    ],
    "food_tour": [
        [("poi_search", lambda p: {"address": "美食 餐厅", "region": p["destination"]}),
         ("weather", lambda p: {"city": p["destination"]})],
        [("poi_search", lambda p: {"address": "小吃街", "region": p["destination"]}),
         ("around_search", None)],
        [("search_train_tickets", lambda p: {"date": p["date"], "from_city": p.get("origin", p["destination"]), "to_city": p["destination"]})],
        "direction_step",
    ],
    "business": [
        [("search_flights", lambda p: {"date": p["date"], "from_city": p["origin"], "to_city": p["destination"]}),
         ("search_train_tickets", lambda p: {"date": p["date"], "from_city": p["origin"], "to_city": p["destination"]})],
        [("poi_search", lambda p: {"address": "商务酒店 会议", "region": p["destination"]}),
         ("weather", lambda p: {"city": p["destination"]})],
        [("poi_search", lambda p: {"address": "商务餐厅 接待", "region": p["destination"]})],
        "direction_step",
        "around_step",
    ],
    # === Phase 1 diversity types ===
    "weekend_escape": [
        [("weather", lambda p: {"city": p["origin"]})],
        [("poi_search", lambda p: {"address": "周边旅游景点", "region": p["origin"]})],
        [("search_train_tickets", lambda p: {"date": p["date"], "from_city": p["origin"], "to_city": p.get("_suggested_dest", p["origin"])})],
        [("poi_search", lambda p: {"address": "酒店 住宿", "region": p.get("_suggested_dest", p["origin"])})],
        "around_step",
        "direction_step",
    ],
    "half_day": [
        [("poi_search", lambda p: {"address": "景点", "region": p.get("destination", p["origin"])})],
        "direction_step",
        [("weather", lambda p: {"city": p.get("destination", p["origin"])})],
        "around_step",
    ],
    "budget_trip": [
        [("search_train_tickets", lambda p: {"date": p["date"], "from_city": p["origin"], "to_city": p["destination"]})],
        [("poi_search", lambda p: {"address": "免费景点 公园", "region": p["destination"]})],
        [("weather", lambda p: {"city": p["destination"]})],
        "around_step_budget",
        "direction_step_walk",
    ],
    "no_direct": [
        [("search_flights", lambda p: {"date": p["date"], "from_city": p["origin"], "to_city": p["destination"]}),
         ("search_train_tickets", lambda p: {"date": p["date"], "from_city": p["origin"], "to_city": p["destination"]})],
        "transfer_step",
        [("poi_search", lambda p: {"address": "景点", "region": p["destination"]}),
         ("weather", lambda p: {"city": p["destination"]})],
        "direction_step",
        "around_step",
    ],
    "bad_weather": [
        [("weather", lambda p: {"city": p["destination"]})],
        [("poi_search", lambda p: {"address": "景点", "region": p["destination"]})],
        "indoor_poi_step",
        [("search_train_tickets", lambda p: {"date": p["date"], "from_city": p["origin"], "to_city": p["destination"]})],
        "direction_step",
        "around_step",
    ],
    "photo_route": [
        [("weather", lambda p: {"city": p["destination"]})],
        [("poi_search", lambda p: {"address": "观景台 日出", "region": p["destination"]})],
        [("poi_search", lambda p: {"address": "夜景 拍摄点", "region": p["destination"]})],
        [("search_train_tickets", lambda p: {"date": p["date"], "from_city": p["origin"], "to_city": p["destination"]})],
        "direction_step",
        "direction_step_2",
        "around_step",
    ],
    "mid_change": [
        [("search_flights", lambda p: {"date": p["date"], "from_city": p["origin"], "to_city": p["destination"]}),
         ("search_train_tickets", lambda p: {"date": p["date"], "from_city": p["origin"], "to_city": p["destination"]})],
        [("poi_search", lambda p: {"address": "酒店", "region": p["destination"]})],
        "user_change_step",
        [("search_flights", lambda p: {"date": p["date"], "from_city": p["origin"], "to_city": p["alt_destination"]}),
         ("search_train_tickets", lambda p: {"date": p["date"], "from_city": p["origin"], "to_city": p["alt_destination"]})],
        [("poi_search", lambda p: {"address": "景点", "region": p["alt_destination"]}),
         ("weather", lambda p: {"city": p["alt_destination"]})],
        "direction_step",
        "around_step",
    ],
    "empty_result": [
        [("poi_search", lambda p: {"address": "景点 旅游", "region": p["destination"]})],
        [("search_train_tickets", lambda p: {"date": p["date"], "from_city": p["origin"], "to_city": p["destination"]})],
        "fallback_around_step",
        [("weather", lambda p: {"city": p["destination"]})],
        "direction_step",
    ],
    # === Eval-aligned types (single_poi, family_study) ===
    # single_poi: must=poi_search+weather, should=around_search, nice=direction
    "single_poi": [
        [("poi_search", lambda p: {"address": p.get("poi_focus", "景点"), "region": p["destination"]}),
         ("weather", lambda p: {"city": p["destination"]})],
        [("poi_search", lambda p: {"address": "餐厅 特色小吃", "region": p["destination"]})],
        "around_step",
        "direction_step",
    ],
    # family_study: must=poi_search+weather, should=direction, nice=around_search
    "family_study": [
        [("poi_search", lambda p: {"address": p.get("study_theme", "博物馆"), "region": p["destination"]}),
         ("weather", lambda p: {"city": p["destination"]})],
        [("poi_search", lambda p: {"address": "亲子景点 儿童乐园", "region": p["destination"]}),
         ("poi_search", lambda p: {"address": "亲子酒店 家庭房", "region": p["destination"]})],
        "direction_step",
        "around_step",
    ],
}
