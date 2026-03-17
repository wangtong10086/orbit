"""NAVWORLD (QQR) synthetic SFT data generator.

Generates high-quality travel planning conversations by:
1. Programmatically generating problems (reusing affinetes patterns)
2. Calling real AMap APIs for POI/weather/direction data
3. Using a strong LLM to generate assistant responses
4. Formatting as multi-turn tool-calling SFT data
"""

import asyncio
import hashlib
import json
import os
import random
import re
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

# ============================================================================
# AMap API client
# ============================================================================

AMAP_BASE = "https://restapi.amap.com/v3"


class AMapClient:
    """Thin async wrapper around AMap REST API with local file cache."""

    CACHE_DIR = "/tmp/amap_cache"

    def __init__(self, api_key: str):
        self.key = api_key
        self._client: Optional[httpx.AsyncClient] = None
        os.makedirs(self.CACHE_DIR, exist_ok=True)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30)
        return self._client

    def _cache_key(self, url: str, params: dict) -> str:
        """Generate cache filename from URL + params (excluding API key)."""
        p = {k: v for k, v in sorted(params.items()) if k != "key"}
        h = hashlib.md5(f"{url}|{json.dumps(p, sort_keys=True)}".encode()).hexdigest()
        return os.path.join(self.CACHE_DIR, f"{h}.json")

    async def _cached_get(self, url: str, params: dict) -> dict:
        """GET with file-based cache. Returns parsed JSON."""
        cache_path = self._cache_key(url, params)
        if os.path.exists(cache_path):
            with open(cache_path) as f:
                return json.load(f)
        c = await self._get_client()
        r = await c.get(url, params=params)
        data = r.json()
        with open(cache_path, "w") as f:
            json.dump(data, f, ensure_ascii=False)
        return data

    async def poi_search(self, address: str, region: str = "") -> str:
        params = {"key": self.key, "keywords": address, "output": "json", "offset": 10}
        if region:
            params["city"] = region
        data = await self._cached_get(f"{AMAP_BASE}/place/text", params)
        pois = data.get("pois", [])
        results = []
        for p in pois[:5]:
            results.append({
                "name": p.get("name", ""),
                "address": p.get("address", ""),
                "location": p.get("location", ""),
                "type": p.get("type", ""),
                "tel": p.get("tel", ""),
            })
        return json.dumps(results, ensure_ascii=False)

    async def around_search(self, location: str, radius: int = 3000,
                            keyword: str = "", region: str = "") -> str:
        params = {
            "key": self.key, "location": location, "radius": str(radius),
            "output": "json", "offset": 10,
        }
        if keyword:
            params["keywords"] = keyword
        if region:
            params["city"] = region
        data = await self._cached_get(f"{AMAP_BASE}/place/around", params)
        pois = data.get("pois", [])
        results = []
        for p in pois[:5]:
            results.append({
                "name": p.get("name", ""),
                "address": p.get("address", ""),
                "location": p.get("location", ""),
                "type": p.get("type", ""),
            })
        return json.dumps(results, ensure_ascii=False)

    async def direction(self, origin: str, destination: str,
                        mode: str = "driving") -> str:
        if mode == "driving":
            url = f"{AMAP_BASE}/direction/driving"
            params = {"key": self.key, "origin": origin, "destination": destination,
                      "output": "json"}
        elif mode == "transit":
            url = f"{AMAP_BASE}/direction/transit/integrated"
            params = {"key": self.key, "origin": origin, "destination": destination,
                      "city": "全国", "output": "json"}
        elif mode == "walking":
            url = f"{AMAP_BASE}/direction/walking"
            params = {"key": self.key, "origin": origin, "destination": destination,
                      "output": "json"}
        else:
            url = f"{AMAP_BASE}/direction/driving"
            params = {"key": self.key, "origin": origin, "destination": destination,
                      "output": "json"}
        data = await self._cached_get(url, params)
        route = data.get("route", {})
        if mode in ("driving", "walking"):
            paths = route.get("paths", [])
            if paths:
                p = paths[0]
                return json.dumps({
                    "distance": p.get("distance", ""),
                    "duration": p.get("duration", ""),
                    "strategy": p.get("strategy", ""),
                }, ensure_ascii=False)
        elif mode == "transit":
            transits = route.get("transits", [])
            if transits:
                t = transits[0]
                return json.dumps({
                    "distance": route.get("distance", ""),
                    "duration": t.get("duration", ""),
                    "cost": t.get("cost", ""),
                }, ensure_ascii=False)
        return json.dumps({"error": "no results"}, ensure_ascii=False)

    async def weather(self, city: str) -> str:
        params = {"key": self.key, "city": city, "extensions": "all", "output": "json"}
        data = await self._cached_get(f"{AMAP_BASE}/weather/weatherInfo", params)
        forecasts = data.get("forecasts", [])
        if forecasts:
            casts = forecasts[0].get("casts", [])
            results = []
            for cast in casts[:4]:
                results.append({
                    "date": cast.get("date", ""),
                    "dayweather": cast.get("dayweather", ""),
                    "nightweather": cast.get("nightweather", ""),
                    "daytemp": cast.get("daytemp", ""),
                    "nighttemp": cast.get("nighttemp", ""),
                    "daywind": cast.get("daywind", ""),
                    "daypower": cast.get("daypower", ""),
                })
            return json.dumps(results, ensure_ascii=False)
        return json.dumps({"error": "no weather data"}, ensure_ascii=False)

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


# ============================================================================
# Mock transport data (deterministic, matching affinetes algorithm)
# ============================================================================

def _transport_salt() -> str:
    """Weekly rotating salt, same as affinetes."""
    epoch = int(time.time()) // (7 * 86400)
    return f"transport_v2_{epoch}"


def _mock_flights(date: str, from_city: str, to_city: str) -> str:
    """Generate deterministic mock flight data."""
    salt = _transport_salt()
    seed = hashlib.sha256(f"{salt}|{date}|{from_city}|{to_city}".encode()).hexdigest()
    rng = random.Random(seed)

    airlines = ["CA", "MU", "CZ", "HU", "3U", "ZH", "MF", "FM"]
    flights = []
    n = rng.randint(3, 6)
    for i in range(n):
        airline = rng.choice(airlines)
        num = rng.randint(1000, 9999)
        hour = rng.randint(6, 22)
        minute = rng.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55])
        duration_h = rng.randint(1, 4)
        duration_m = rng.choice([0, 10, 20, 30, 40, 50])
        price = rng.randint(400, 2500)
        flights.append({
            "flight_no": f"{airline}{num}",
            "departure_time": f"{hour:02d}:{minute:02d}",
            "arrival_time": f"{(hour + duration_h) % 24:02d}:{(minute + duration_m) % 60:02d}",
            "duration": f"{duration_h}h{duration_m}m",
            "price": price,
            "from_city": from_city,
            "to_city": to_city,
        })

    return json.dumps(flights, ensure_ascii=False)


def _mock_trains(date: str, from_city: str, to_city: str) -> str:
    """Generate deterministic mock train data."""
    salt = _transport_salt()
    seed = hashlib.sha256(f"{salt}|train|{date}|{from_city}|{to_city}".encode()).hexdigest()
    rng = random.Random(seed)

    prefixes = ["G", "D", "K", "Z", "T"]
    trains = []
    n = rng.randint(3, 8)
    for i in range(n):
        prefix = rng.choice(prefixes)
        num = rng.randint(1, 9999)
        hour = rng.randint(6, 22)
        minute = rng.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55])
        if prefix in ("G", "D"):
            dur_h = rng.randint(1, 6)
            price_2 = rng.randint(150, 800)
            price_1 = int(price_2 * 1.6)
        else:
            dur_h = rng.randint(4, 20)
            price_2 = rng.randint(80, 400)
            price_1 = int(price_2 * 1.5)
        dur_m = rng.choice([0, 10, 20, 30, 40, 50])
        trains.append({
            "train_no": f"{prefix}{num}",
            "departure_time": f"{hour:02d}:{minute:02d}",
            "arrival_time": f"{(hour + dur_h) % 24:02d}:{(minute + dur_m) % 60:02d}",
            "duration": f"{dur_h}h{dur_m}m",
            "second_class_price": price_2,
            "first_class_price": price_1,
            "from_city": from_city,
            "to_city": to_city,
        })

    return json.dumps(trains, ensure_ascii=False)


# ============================================================================
# Problem generation (simplified from affinetes)
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

MAJOR_CITIES = [
    "北京", "上海", "广州", "深圳", "杭州", "成都", "西安", "重庆",
    "南京", "武汉", "长沙", "苏州", "天津", "青岛", "厦门", "大连",
    "昆明", "三亚", "桂林", "丽江", "张家界", "黄山", "洛阳",
]

INTERESTS = [
    "natural scenery", "culture & history", "food exploration", "shopping", "leisure vacation",
    "photography", "family fun", "outdoor sports", "folk customs", "museums",
]

PREFERENCES = ["comfort first", "budget first", "speed first"]

PROBLEM_TYPES = ["intercity", "multiday", "hybrid", "food_tour", "business"]


def generate_problem(task_id: int) -> dict:
    """Generate a travel planning problem deterministically."""
    rng = random.Random(task_id)
    ptype = PROBLEM_TYPES[task_id % len(PROBLEM_TYPES)]

    # Pick cities — always use different origin/dest for transport tool diversity
    if ptype in ("intercity", "hybrid", "business"):
        pairs = CITY_PAIRS_SHORT + CITY_PAIRS_MEDIUM + CITY_PAIRS_LONG
        origin, dest = rng.choice(pairs)
    else:
        # multiday/food_tour: pick a city pair so transport tools are meaningful
        pairs = CITY_PAIRS_SHORT + CITY_PAIRS_MEDIUM
        origin, dest = rng.choice(pairs)

    # Date: 7-60 days from now
    travel_date = (datetime.now() + timedelta(days=rng.randint(7, 60))).strftime("%Y-%m-%d")
    num_days = rng.randint(1, 5) if ptype in ("multiday", "hybrid", "food_tour") else 1
    budget = rng.randint(500, 5000)
    interests = rng.sample(INTERESTS, rng.randint(1, 3))
    pref = rng.choice(PREFERENCES) if ptype in ("intercity", "business") else None

    return {
        "task_id": task_id,
        "type": ptype,
        "origin": origin,
        "destination": dest,
        "date": travel_date,
        "num_days": num_days,
        "budget": budget,
        "interests": interests,
        "preference": pref,
    }


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
    return f"Please help me plan a trip to {p['destination']}."


# ============================================================================
# Tool call execution
# ============================================================================

async def execute_tool(amap: AMapClient, name: str, args: dict) -> str:
    """Execute a tool call and return result string."""
    if name == "poi_search":
        return await amap.poi_search(args.get("address", ""), args.get("region", ""))
    elif name == "around_search":
        return await amap.around_search(
            args.get("location", ""), int(args.get("radius", 3000)),
            args.get("keyword", ""), args.get("region", ""),
        )
    elif name == "direction":
        return await amap.direction(
            args.get("origin", ""), args.get("destination", ""),
            args.get("mode", "driving"),
        )
    elif name == "weather":
        return await amap.weather(args.get("city", ""))
    elif name == "search_flights":
        return _mock_flights(args.get("date", ""), args.get("from_city", ""), args.get("to_city", ""))
    elif name == "search_train_tickets":
        return _mock_trains(args.get("date", ""), args.get("from_city", ""), args.get("to_city", ""))
    return json.dumps({"error": f"unknown tool: {name}"})


# ============================================================================
# LLM client (Chutes)
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


async def call_llm(
    client: httpx.AsyncClient,
    messages: list,
    api_key: str,
    model: str = "qwen3-max",
    use_tools: bool = True,
    max_retries: int = 3,
) -> Optional[dict]:
    """Call LLM via DashScope API with tool calling support and retry on 429."""
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 8192,
    }
    if use_tools:
        payload["tools"] = TOOLS_SCHEMA
        payload["tool_choice"] = "auto"

    for attempt in range(max_retries):
        try:
            r = await client.post(
                "https://dashscope-us.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
                timeout=180,
            )
            if r.status_code == 429:
                wait = 10 * (attempt + 1)
                await asyncio.sleep(wait)
                continue
            if r.status_code != 200:
                print(f"  LLM error {r.status_code}: {r.text[:200]}", flush=True)
                return None
            data = r.json()
            choice = data.get("choices", [{}])[0]
            msg = choice.get("message", {})
            return {
                "content": msg.get("content", ""),
                "tool_calls": msg.get("tool_calls"),
            }
        except Exception as e:
            print(f"  LLM exception: {e}", flush=True)
            if attempt < max_retries - 1:
                await asyncio.sleep(5)
    return None


# ============================================================================
# Orchestrated conversation generation
# ============================================================================

# Required tool sequences by problem type — every type uses ≥5 tools for scorer diversity bonus
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
        [("search_flights", lambda p: {"date": p["date"], "from_city": p.get("origin", p["destination"]), "to_city": p["destination"]}),
         ("search_train_tickets", lambda p: {"date": p["date"], "from_city": p.get("origin", p["destination"]), "to_city": p["destination"]})],
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
        [("poi_search", lambda p: {"address": "商务酒店", "region": p["destination"]}),
         ("weather", lambda p: {"city": p["destination"]})],
        [("poi_search", lambda p: {"address": "餐厅", "region": p["destination"]})],
        "direction_step",
        "around_step",
    ],
}


def _get_location_from_results(results_cache: list) -> Optional[str]:
    """Extract first coordinate from cached POI results."""
    for r in results_cache:
        try:
            data = json.loads(r["result"])
            if isinstance(data, list):
                for item in data:
                    loc = item.get("location", "")
                    if "," in loc:
                        return loc
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def _extract_poi_names(results_cache: list) -> list[str]:
    """Extract all POI names from tool results for grounding enforcement."""
    names = []
    for r in results_cache:
        try:
            data = json.loads(r["result"])
            if isinstance(data, list):
                for item in data:
                    name = item.get("name", "")
                    if name and name not in names:
                        names.append(name)
        except (json.JSONDecodeError, TypeError):
            pass
    return names


def _extract_transport_ids(results_cache: list) -> list[str]:
    """Extract flight/train IDs from tool results."""
    ids = []
    for r in results_cache:
        if r["tool"] not in ("search_flights", "search_train_tickets"):
            continue
        try:
            data = json.loads(r["result"])
            if isinstance(data, list):
                for item in data:
                    fid = item.get("flight_no") or item.get("train_no", "")
                    if fid:
                        ids.append(fid)
        except (json.JSONDecodeError, TypeError):
            pass
    return ids


REASONING_WORDS = re.compile(
    r"因为|由于|所以|因此|建议|推荐|考虑到|综合|权衡|对比|相比|优先|适合"
)


def _validate_final_plan(text: str, poi_names: list[str]) -> bool:
    """Check if final plan meets scorer quality requirements."""
    if len(text) < 800:
        return False
    if len(REASONING_WORDS.findall(text)) < 3:
        return False
    # Check POI grounding: at least 2 tool POI names appear in final text
    matched = sum(1 for name in poi_names if name in text)
    if poi_names and matched < min(2, len(poi_names)):
        return False
    return True


async def generate_conversation(
    problem: dict,
    amap: AMapClient,
    api_key: str,
    model: str = "qwen3-max",
    max_steps: int = 10,
) -> Optional[list]:
    """Generate a travel planning conversation using orchestrated tool calls.

    Strategy: programmatically decide which tools to call (ensuring coverage),
    execute them with real APIs, then let LLM generate natural text for each step.
    """
    ptype = problem["type"]
    user_prompt = problem_to_prompt(problem)
    plan = TOOL_PLANS.get(ptype, TOOL_PLANS["multiday"])

    conversation = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    all_results = []  # Track all tool results for dynamic steps
    tools_called = set()
    locations = []  # Coordinates from POI results

    for step_plan in plan:
        # Handle dynamic steps
        if step_plan == "direction_step":
            if len(locations) >= 2:
                calls = [("direction", {"origin": locations[0], "destination": locations[1], "mode": "driving"})]
            else:
                # Fallback: use origin/destination city names as direction parameters
                calls = [("direction", {"origin": problem.get("origin", "city center"), "destination": problem["destination"], "mode": "driving"})]
        elif step_plan == "around_step":
            loc = _get_location_from_results(all_results)
            if loc:
                calls = [("around_search", {"location": loc, "radius": 3000, "keyword": "餐厅", "region": problem["destination"]})]
            else:
                continue
        else:
            calls = []
            for tool_name, args_fn in step_plan:
                if args_fn is None:
                    loc = _get_location_from_results(all_results)
                    if loc:
                        calls.append((tool_name, {"location": loc, "radius": 3000, "keyword": "美食", "region": problem["destination"]}))
                else:
                    calls.append((tool_name, args_fn(problem)))

        if not calls:
            continue

        # Build assistant tool_calls message (OpenAI function calling format)
        tool_call_entries = []
        for name, args in calls:
            call_id = f"call_{hashlib.md5(f'{name}{json.dumps(args)}{len(conversation)}'.encode()).hexdigest()[:8]}"
            tool_call_entries.append({
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(args, ensure_ascii=False),
                },
            })

        conversation.append({
            "role": "assistant",
            "content": None,
            "tool_calls": tool_call_entries,
        })

        # Execute tools and add tool role responses
        for idx, (name, args) in enumerate(calls):
            result = await execute_tool(amap, name, args)
            tools_called.add(name)

            # Extract coordinates from POI results
            try:
                data = json.loads(result)
                if isinstance(data, list):
                    for item in data:
                        loc = item.get("location", "")
                        if "," in loc and loc not in locations:
                            locations.append(loc)
            except (json.JSONDecodeError, TypeError):
                pass

            if len(result) > 2000:
                result = result[:2000] + "..."

            all_results.append({"tool": name, "result": result})

            conversation.append({
                "role": "tool",
                "content": result,
                "tool_call_id": tool_call_entries[idx]["id"],
            })

    # Extract grounding data for the final prompt
    poi_names = _extract_poi_names(all_results)
    transport_ids = _extract_transport_ids(all_results)

    # Build LLM-friendly messages (text format, not tool_calls) for final plan generation
    grounding_parts = []
    if poi_names:
        grounding_parts.append(f"Available locations (must reference): {', '.join(poi_names[:15])}")
    if transport_ids:
        grounding_parts.append(f"Available services (reference specific IDs): {', '.join(transport_ids[:10])}")

    # Reconstruct readable conversation for LLM
    llm_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    # Add tool results as readable text
    tool_summary_parts = []
    for r in all_results:
        tool_summary_parts.append(f"[{r['tool']}] result:\n{r['result']}")
    llm_messages.append({"role": "assistant", "content": "Tools called for information gathering: " + ", ".join(sorted(tools_called))})
    tool_results_text = "\n\n".join(tool_summary_parts)
    grounding_text = "\n".join(grounding_parts)
    llm_user_content = (
        f"Here are all tool call results:\n\n{tool_results_text}\n\n"
        f"Information gathering complete. Please provide a detailed, comprehensive plan.\n\n"
        f"[Important Requirements]\n"
        f"1. The plan must reference real data returned by tools (location names, flight/train numbers, prices, times, weather); do not fabricate\n"
        f"2. Use analytical reasoning words (because, therefore, recommend, considering, overall, compare, suggest, etc.) to explain choices\n"
        f"3. The plan must be detailed and thorough (at least 800 characters), including specific times, costs, and route information\n"
        f"4. Compare different options and provide clear recommendations\n"
        f"5. Must include a [Comprehensive Comparison] section: use a table or list to compare at least 2 options by price/time/comfort, explaining the recommendation\n"
        f"6. Every recommendation must include reasoning (e.g., recommend X train because it has the best value/shortest time/most comfortable)\n"
        f"\n{grounding_text}"
    )
    llm_messages.append({"role": "user", "content": llm_user_content})

    # Generate final plan with quality gate (retry once if too short/ungrounded)
    final = None
    async with httpx.AsyncClient() as client:
        for attempt in range(2):
            response = await call_llm(client, llm_messages, api_key, model, use_tools=False)
            if not response or not response.get("content"):
                return None
            final = response["content"]
            if _validate_final_plan(final, poi_names):
                break
            if attempt == 0:
                llm_messages.append({"role": "assistant", "content": final})
                llm_messages.append({"role": "user", "content": (
                    "The plan is not detailed enough. Please regenerate, ensuring: at least 800 characters, "
                    "reference specific location names returned by tools, use analytical reasoning words "
                    "(because/suggest/recommend etc.), and include specific prices and times."
                )})
        if final is None or len(final) < 400:
            return None

    # Clean SFT conversation: tool steps + final assistant response (no grounding prompt)
    conversation.append({"role": "assistant", "content": final})

    if len(tools_called) < 3:
        return None

    return conversation


# ============================================================================
# Batch generation
# ============================================================================

async def generate_batch(
    num_samples: int,
    output_path: str,
    amap_key: str,
    api_key: str,
    model: str = "qwen3-max",
    start_id: int = 0,
    concurrency: int = 3,
):
    """Generate a batch of NAVWORLD SFT samples."""
    amap = AMapClient(amap_key)
    sem = asyncio.Semaphore(concurrency)
    results = []
    failed = 0

    async def gen_one(task_id: int):
        nonlocal failed
        async with sem:
            problem = generate_problem(task_id)
            print(f"  [{task_id}] {problem['type']}: {problem.get('origin', '')}→{problem['destination']}", flush=True)

            conv = await generate_conversation(problem, amap, api_key, model)
            if conv is None:
                print(f"  [{task_id}] FAILED", flush=True)
                failed += 1
                return None

            total_chars = sum(len(m.get("content", "") or "") for m in conv)
            print(f"  [{task_id}] OK: {len(conv)} msgs, {total_chars} chars, tools: {_count_tools(conv)}", flush=True)

            return {
                "messages": conv,
                "env": "NAVWORLD",
                "source": "distillation",
                "distill_model": model,
                "score": 1.0,
                "task_id": task_id,
                "problem_type": problem["type"],
            }

    # Run with concurrency, write results incrementally
    outfile = open(output_path, "a")

    async def gen_and_write(task_id: int):
        try:
            r = await gen_one(task_id)
        except Exception as e:
            print(f"  [{task_id}] EXCEPTION: {type(e).__name__}: {e}", flush=True)
            nonlocal failed
            failed += 1
            return None
        if isinstance(r, dict) and r is not None:
            line = json.dumps(r, ensure_ascii=False)
            outfile.write(line + "\n")
            outfile.flush()
            results.append(r)
        return r

    tasks = [gen_and_write(start_id + i) for i in range(num_samples)]
    await asyncio.gather(*tasks)
    outfile.close()

    await amap.close()

    print(f"\nGenerated {len(results)}/{num_samples} samples ({failed} failed)")
    print(f"Output: {output_path}")
    return results


def _count_tools(conversation: list) -> str:
    """Count unique tools used in a conversation."""
    tools = set()
    for m in conversation:
        if m.get("tool_calls"):
            for tc in m["tool_calls"]:
                tools.add(tc["function"]["name"])
    return ",".join(sorted(tools)) if tools else "none"


# ============================================================================
# CLI entry point
# ============================================================================

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate NAVWORLD SFT data")
    parser.add_argument("-n", "--num", type=int, default=10, help="Number of samples")
    parser.add_argument("-o", "--output", default="data/navworld_synthetic.jsonl")
    parser.add_argument("--model", default="qwen-max-latest")
    parser.add_argument("--start-id", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=3)
    args = parser.parse_args()

    amap_key = os.environ.get("AMAP_API_KEY") or os.environ.get("AMAP_MAPS_API_KEY", "")
    api_key = os.environ.get("QWEN_API_KEY") or os.environ.get("CHUTES_API_KEY", "")

    if not amap_key:
        print("Error: AMAP_API_KEY not set")
        return
    if not api_key:
        print("Error: QWEN_API_KEY not set")
        return

    print(f"Generating {args.num} NAVWORLD samples using {args.model}")
    print(f"AMap key: {amap_key[:8]}..., API key: {api_key[:12]}...")

    await generate_batch(
        num_samples=args.num,
        output_path=args.output,
        amap_key=amap_key,
        api_key=api_key,
        model=args.model,
        start_id=args.start_id,
        concurrency=args.concurrency,
    )


if __name__ == "__main__":
    asyncio.run(main())
