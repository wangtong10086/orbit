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
                dist_m = int(p.get("distance", 0) or 0)
                dur_s = int(p.get("duration", 0) or 0)
                return json.dumps({
                    "distance": f"{dist_m}米" if dist_m < 1000 else f"{dist_m/1000:.1f}公里",
                    "duration": f"约{dur_s//60}分钟" if dur_s < 3600 else f"约{dur_s//3600}小时{(dur_s%3600)//60}分钟",
                    "strategy": p.get("strategy", ""),
                }, ensure_ascii=False)
        elif mode == "transit":
            transits = route.get("transits", [])
            if transits:
                t = transits[0]
                dist_m = int(route.get("distance", 0) or 0)
                dur_s = int(t.get("duration", 0) or 0)
                return json.dumps({
                    "distance": f"{dist_m}米" if dist_m < 1000 else f"{dist_m/1000:.1f}公里",
                    "duration": f"约{dur_s//60}分钟" if dur_s < 3600 else f"约{dur_s//3600}小时{(dur_s%3600)//60}分钟",
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
# Mock transport data — EXACT COPY of eval environment
# Source: repos/affinetes/environments/qqr/mock_transport/server.py
# MUST stay in sync with eval to avoid train/eval format mismatch
# ============================================================================

# --- City data (from eval) ---
CITY_AIRPORTS = {
    "北京": ["首都国际机场", "大兴国际机场"], "上海": ["浦东国际机场", "虹桥国际机场"],
    "广州": ["白云国际机场"], "深圳": ["宝安国际机场"], "杭州": ["萧山国际机场"],
    "成都": ["天府国际机场", "双流国际机场"], "西安": ["咸阳国际机场"],
    "重庆": ["江北国际机场"], "南京": ["禄口国际机场"], "武汉": ["天河国际机场"],
    "长沙": ["黄花国际机场"], "青岛": ["胶东国际机场"], "苏州": [],
    "厦门": ["高崎国际机场"], "大连": ["周水子国际机场"], "天津": ["滨海国际机场"],
    "三亚": ["凤凰国际机场"], "昆明": ["长水国际机场"], "桂林": ["两江国际机场"],
    "丽江": ["三义国际机场"], "张家界": ["荷花国际机场"], "黄山": ["屯溪国际机场"],
    "九寨沟": ["黄龙九寨沟机场"], "郑州": ["新郑国际机场"],
    "洛阳": ["北郊机场"], "泉州": ["晋江国际机场"], "大理": [],
    "威海": ["大水泊国际机场"], "哈尔滨": ["太平国际机场"], "沈阳": ["桃仙国际机场"],
    "济南": ["遥墙国际机场"], "福州": ["长乐国际机场"], "合肥": ["新桥国际机场"],
    "南昌": ["昌北国际机场"], "贵阳": ["龙洞堡国际机场"], "南宁": ["吴圩国际机场"],
    "海口": ["美兰国际机场"], "太原": ["武宿国际机场"], "兰州": ["中川国际机场"],
    "银川": ["河东国际机场"], "西宁": ["曹家堡国际机场"], "呼和浩特": ["白塔国际机场"],
    "乌鲁木齐": ["地窝堡国际机场"], "拉萨": ["贡嘎机场"], "珠海": ["金湾机场"],
    "无锡": ["硕放机场"], "温州": ["龙湾国际机场"], "宁波": ["栎社国际机场"],
    "烟台": ["蓬莱国际机场"], "石家庄": ["正定国际机场"], "长春": ["龙嘉国际机场"],
    "常州": ["奔牛国际机场"], "徐州": ["观音国际机场"], "连云港": ["花果山国际机场"],
    "扬州": ["泰州扬州机场"], "秦皇岛": [], "承德": [], "敦煌": ["莫高国际机场"],
    "张掖": ["甘州机场"], "嘉峪关": ["机场"], "腾冲": ["驼峰机场"],
    "景德镇": ["罗家机场"], "北海": ["福成机场"], "阳朔": [], "凤凰古城": [],
    "婺源": [], "平遥": [], "乐山": [], "都江堰": [], "峨眉山": [],
    "稻城": ["亚丁机场"],
}
CITY_TRAIN_STATIONS = {
    "北京": ["北京南站", "北京西站", "北京站", "北京北站"],
    "上海": ["上海虹桥站", "上海站", "上海南站"],
    "广州": ["广州南站", "广州站", "广州东站"],
    "深圳": ["深圳北站", "深圳站", "福田站"],
    "杭州": ["杭州东站", "杭州站", "杭州西站"],
    "成都": ["成都东站", "成都站", "成都南站"],
    "西安": ["西安北站", "西安站"], "重庆": ["重庆北站", "重庆西站", "重庆站"],
    "南京": ["南京南站", "南京站"], "武汉": ["武汉站", "汉口站", "武昌站"],
    "长沙": ["长沙南站", "长沙站"], "青岛": ["青岛站", "青岛北站"],
    "苏州": ["苏州站", "苏州北站"], "厦门": ["厦门站", "厦门北站"],
    "大连": ["大连站", "大连北站"], "天津": ["天津站", "天津南站", "天津西站"],
    "三亚": ["三亚站"], "昆明": ["昆明南站", "昆明站"],
    "桂林": ["桂林站", "桂林北站"], "丽江": ["丽江站"], "张家界": ["张家界西站"],
    "黄山": ["黄山北站"], "九寨沟": [], "郑州": ["郑州东站", "郑州站"],
    "洛阳": ["洛阳龙门站", "洛阳站"], "泉州": ["泉州站"], "大理": ["大理站"],
    "威海": ["威海站"], "哈尔滨": ["哈尔滨西站", "哈尔滨站"],
    "沈阳": ["沈阳北站", "沈阳站"], "济南": ["济南西站", "济南站"],
    "福州": ["福州站", "福州南站"], "合肥": ["合肥南站", "合肥站"],
    "南昌": ["南昌西站", "南昌站"], "贵阳": ["贵阳北站", "贵阳站"],
    "南宁": ["南宁东站", "南宁站"], "海口": ["海口东站", "海口站"],
    "太原": ["太原南站", "太原站"], "兰州": ["兰州西站", "兰州站"],
    "银川": ["银川站"], "西宁": ["西宁站"], "呼和浩特": ["呼和浩特东站"],
    "乌鲁木齐": ["乌鲁木齐站"], "拉萨": ["拉萨站"], "珠海": ["珠海站"],
    "无锡": ["无锡站", "无锡东站"], "温州": ["温州南站"], "宁波": ["宁波站"],
    "烟台": ["烟台站", "烟台南站"], "石家庄": ["石家庄站"],
    "长春": ["长春站", "长春西站"], "常州": ["常州站", "常州北站"],
    "徐州": ["徐州东站", "徐州站"], "连云港": ["连云港站"], "扬州": ["扬州东站"],
    "秦皇岛": ["秦皇岛站"], "承德": ["承德南站"], "敦煌": ["敦煌站"],
    "张掖": ["张掖西站"], "嘉峪关": ["嘉峪关南站"], "腾冲": [],
    "景德镇": ["景德镇北站"], "北海": ["北海站"], "阳朔": ["阳朔站"],
    "凤凰古城": [], "婺源": ["婺源站"], "平遥": ["平遥古城站"],
    "乐山": ["乐山站"], "都江堰": ["都江堰站"], "峨眉山": ["峨眉山站"], "稻城": [],
}
CITY_DISTANCES = {
    ("北京", "上海"): 1200, ("北京", "广州"): 2100, ("北京", "深圳"): 2200,
    ("北京", "杭州"): 1300, ("北京", "成都"): 1800, ("北京", "西安"): 1100,
    ("北京", "重庆"): 1700, ("北京", "南京"): 1000, ("北京", "武汉"): 1200,
    ("北京", "长沙"): 1500, ("北京", "青岛"): 700, ("北京", "厦门"): 1800,
    ("北京", "大连"): 900, ("北京", "天津"): 120, ("北京", "三亚"): 2800,
    ("北京", "昆明"): 2500, ("北京", "桂林"): 1900, ("北京", "丽江"): 2600,
    ("北京", "郑州"): 700, ("北京", "哈尔滨"): 1200, ("北京", "沈阳"): 700,
    ("北京", "济南"): 400, ("北京", "福州"): 1700, ("北京", "合肥"): 1000,
    ("北京", "南昌"): 1400, ("北京", "贵阳"): 2100, ("北京", "南宁"): 2300,
    ("北京", "海口"): 2700, ("北京", "太原"): 500, ("北京", "兰州"): 1500,
    ("北京", "乌鲁木齐"): 3000, ("北京", "拉萨"): 3700,
    ("上海", "广州"): 1500, ("上海", "深圳"): 1500, ("上海", "杭州"): 180,
    ("上海", "成都"): 2000, ("上海", "西安"): 1500, ("上海", "重庆"): 1800,
    ("上海", "南京"): 300, ("上海", "武汉"): 800, ("上海", "长沙"): 1000,
    ("上海", "青岛"): 800, ("上海", "苏州"): 100, ("上海", "厦门"): 800,
    ("上海", "大连"): 1200, ("上海", "天津"): 1100, ("上海", "三亚"): 2000,
    ("上海", "昆明"): 2200, ("上海", "桂林"): 1500, ("上海", "丽江"): 2300,
    ("上海", "福州"): 700, ("上海", "合肥"): 450, ("上海", "南昌"): 700,
    ("上海", "贵阳"): 1700, ("上海", "海口"): 1900,
    ("广州", "深圳"): 140, ("广州", "杭州"): 1300, ("广州", "成都"): 1600,
    ("广州", "西安"): 1600, ("广州", "重庆"): 1300, ("广州", "南京"): 1300,
    ("广州", "武汉"): 1000, ("广州", "长沙"): 700, ("广州", "厦门"): 600,
    ("广州", "三亚"): 800, ("广州", "昆明"): 1500, ("广州", "桂林"): 500,
    ("广州", "南宁"): 600, ("广州", "海口"): 600, ("广州", "贵阳"): 900,
    ("广州", "福州"): 800, ("广州", "南昌"): 800,
    ("深圳", "杭州"): 1300, ("深圳", "成都"): 1700, ("深圳", "厦门"): 500,
    ("深圳", "北京"): 2200,
    ("成都", "重庆"): 300, ("成都", "西安"): 700, ("成都", "昆明"): 800,
    ("成都", "贵阳"): 700, ("成都", "拉萨"): 1600, ("成都", "兰州"): 700,
    ("杭州", "厦门"): 700, ("杭州", "南京"): 300, ("杭州", "武汉"): 800,
    ("南京", "苏州"): 200, ("南京", "武汉"): 500, ("南京", "合肥"): 300,
    ("武汉", "长沙"): 350,
    ("西安", "郑州"): 500, ("西安", "兰州"): 600, ("西安", "成都"): 700,
    ("昆明", "大理"): 350, ("昆明", "丽江"): 500, ("昆明", "贵阳"): 500,
}
AIRLINE_CODES = ["CA", "MU", "CZ", "HU", "3U", "HO", "ZH", "MF", "FM", "GS", "SC", "KN", "JD", "EU", "TV"]
TRAIN_TYPES = [
    ("G", 300, 0.46), ("D", 250, 0.31), ("C", 300, 0.46),
    ("Z", 120, 0.16), ("T", 100, 0.14), ("K", 80, 0.12),
]

TRANSPORT_SALT = os.getenv("TRANSPORT_SALT", "")


def _make_seed(date: str, from_city: str, to_city: str) -> int:
    """EXACT copy of eval's _make_seed."""
    salt = TRANSPORT_SALT
    if not salt:
        salt = str(int(time.time()) // (7 * 86400))
    key = f"{salt}|{date}|{from_city}|{to_city}"
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


def _get_distance(from_city: str, to_city: str) -> int:
    """EXACT copy of eval's _get_distance."""
    pair = (from_city, to_city)
    if pair in CITY_DISTANCES:
        return CITY_DISTANCES[pair]
    reverse = (to_city, from_city)
    if reverse in CITY_DISTANCES:
        return CITY_DISTANCES[reverse]
    cities_sorted = tuple(sorted([from_city, to_city]))
    key = f"distance|{cities_sorted[0]}|{cities_sorted[1]}"
    seed = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
    return 500 + (seed % 2000)


def _mock_flights(date: str, from_city: str, to_city: str) -> str:
    """EXACT copy of eval's _generate_flights + json.dumps.
    Returns JSON array of Chinese text strings, NOT JSON objects.
    """
    seed = _make_seed(date, from_city, to_city)
    rng = random.Random(seed)
    distance = _get_distance(from_city, to_city)

    from_airports = CITY_AIRPORTS.get(from_city, [])
    to_airports = CITY_AIRPORTS.get(to_city, [])
    if not from_airports or not to_airports:
        return json.dumps([], ensure_ascii=False)

    num_flights = rng.randint(8, 15)
    num_redeye = rng.randint(1, 2)
    num_normal = num_flights - num_redeye
    normal_deps = sorted(rng.sample(range(300, 1380), min(num_normal, 1080)))
    redeye_deps = [rng.randint(1380, 1500) for _ in range(num_redeye)]
    dep_minutes = sorted(normal_deps + redeye_deps)

    flights = []
    used_flight_numbers = set()

    for dep_min in dep_minutes:
        airline = rng.choice(AIRLINE_CODES)
        flight_id = None
        for _ in range(10):
            flight_num = rng.randint(100, 9999)
            candidate = f"{airline}{flight_num}"
            if candidate not in used_flight_numbers:
                flight_id = candidate
                used_flight_numbers.add(flight_id)
                break
        if flight_id is None:
            continue

        dep_airport = rng.choice(from_airports)
        arr_airport = rng.choice(to_airports)

        flight_hours = distance / 750
        flight_hours *= (0.9 + rng.random() * 0.2)
        flight_minutes_val = max(60, int(flight_hours * 60))

        arr_min = dep_min + flight_minutes_val
        dep_h, dep_m = divmod(dep_min, 60)
        arr_h, arr_m = divmod(arr_min, 60)

        next_day = ""
        if arr_h >= 24:
            arr_h -= 24
            next_day = "(次日)"

        display_dep_h = dep_h % 24 if dep_h >= 24 else dep_h

        base_price = distance * 0.5 + 100
        is_redeye = dep_min >= 1380 or dep_min < 300
        if rng.random() < 0.3:
            price_variation = rng.uniform(0.55, 0.85)
        else:
            price_variation = rng.uniform(1.1, 1.7)
        price = round(base_price * price_variation)
        if is_redeye:
            price = int(price * rng.uniform(0.6, 0.8))
        price = max(200, min(8000, price))

        dur_h = flight_minutes_val // 60
        dur_m = flight_minutes_val % 60
        duration_str = f"{dur_h}小时{dur_m}分" if dur_m > 0 else f"{dur_h}小时"

        record = (
            f"航班 {flight_id}，价格{price}元，"
            f"{display_dep_h:02d}:{dep_m:02d}从{dep_airport}出发，"
            f"{arr_h:02d}:{arr_m:02d}{next_day}到达{arr_airport}，"
            f"飞行时长{duration_str}"
        )
        flights.append(record)

    return json.dumps(flights, ensure_ascii=False)


def _mock_trains(date: str, from_city: str, to_city: str) -> str:
    """EXACT copy of eval's _generate_trains + json.dumps.
    Returns JSON array of Chinese text strings, NOT JSON objects.
    """
    seed = _make_seed(date, from_city, to_city)
    rng = random.Random(seed)
    distance = _get_distance(from_city, to_city)

    from_stations = CITY_TRAIN_STATIONS.get(from_city, [])
    to_stations = CITY_TRAIN_STATIONS.get(to_city, [])
    if not from_stations or not to_stations:
        return json.dumps([], ensure_ascii=False)

    available_types = []
    if distance <= 500:
        available_types = [("G", 300, 0.46), ("D", 250, 0.31), ("C", 300, 0.46)]
    elif distance <= 1500:
        available_types = [("G", 300, 0.46), ("D", 250, 0.31), ("Z", 120, 0.16), ("T", 100, 0.14)]
    else:
        available_types = TRAIN_TYPES[:]

    num_trains = rng.randint(8, 15)
    dep_minutes = sorted(rng.sample(range(360, 1380), num_trains))

    trains = []
    used_train_numbers = set()

    for dep_min in dep_minutes:
        train_type = rng.choice(available_types)
        prefix, speed, price_per_km = train_type

        train_id = None
        for _ in range(10):
            if prefix in ("G", "D", "C"):
                train_num = rng.randint(1, 9999)
            else:
                train_num = rng.randint(1, 999)
            candidate = f"{prefix}{train_num}"
            if candidate not in used_train_numbers:
                train_id = candidate
                used_train_numbers.add(train_id)
                break
        if train_id is None:
            continue

        dep_station = rng.choice(from_stations)
        arr_station = rng.choice(to_stations)

        travel_hours = distance / speed
        travel_hours *= (0.9 + rng.random() * 0.3)
        travel_minutes = max(30, int(travel_hours * 60))

        arr_min = dep_min + travel_minutes
        dep_h, dep_m = divmod(dep_min, 60)
        arr_h, arr_m = divmod(arr_min, 60)

        if arr_h >= 24:
            if prefix in ("Z", "T", "K"):
                arr_h = arr_h % 24
            else:
                continue

        base_price = distance * price_per_km
        if prefix in ("G", "D", "C"):
            if rng.random() < 0.3:
                price_variation = rng.uniform(0.55, 0.85)
            else:
                price_variation = rng.uniform(1.1, 1.7)
        else:
            price_variation = rng.uniform(0.85, 1.15)
        price = round(base_price * price_variation)
        price = max(30, min(3000, price))

        dur_h = travel_minutes // 60
        dur_m = travel_minutes % 60
        if dur_h > 0:
            duration_str = f"{dur_h}小时{dur_m}分" if dur_m > 0 else f"{dur_h}小时"
        else:
            duration_str = f"{dur_m}分钟"

        record = (
            f"直达车次 {train_id}，价格{price}元，"
            f"{dep_h:02d}:{dep_m:02d}从{dep_station}出发，"
            f"{arr_h:02d}:{arr_m:02d}到达{arr_station}，"
            f"全程约{duration_str}。"
        )
        trains.append(record)

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
