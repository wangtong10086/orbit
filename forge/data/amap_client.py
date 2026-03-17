"""AMap API client and transport data for NAVWORLD generation."""

import hashlib
import json
import os
import random
import time
from typing import Optional

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
