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
