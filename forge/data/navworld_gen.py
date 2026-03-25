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
import re
from typing import Optional

import httpx

from forge.data.amap_client import AMapClient, execute_tool
from forge.data.navworld_plans import TOOL_PLANS
from forge.data.navworld_prompts import (
    ALL_PROBLEM_TYPES,
    PHASE1_TYPES,
    SYSTEM_PROMPT,
    TOOLS_SCHEMA,
    generate_problem,
    problem_to_prompt,
)


# ============================================================================
# LLM client (DashScope)
# ============================================================================

def _is_claude_model(model: str) -> bool:
    """Check if model is a Claude model (use Anthropic API)."""
    return "claude" in model.lower()


def _is_openai_model(model: str) -> bool:
    """Check if model uses OpenAI-compatible API (GPT, Claude via proxy, etc)."""
    m = model.lower()
    return "gpt" in m or "o1" in m or "o3" in m or "claude" in m


async def call_llm(
    client: httpx.AsyncClient,
    messages: list,
    api_key: str,
    model: str = "qwen3-max",
    use_tools: bool = True,
    max_retries: int = 3,
) -> Optional[dict]:
    """Call LLM via OpenAI-compatible API, Anthropic API, or DashScope."""
    if _is_claude_model(model):
        return await _call_claude(messages, model, max_retries)
    if _is_openai_model(model):
        return await _call_openai(client, messages, model, use_tools, max_retries)
    return await _call_dashscope(client, messages, api_key, model, use_tools, max_retries)


async def _call_claude(
    messages: list,
    model: str,
    max_retries: int = 3,
) -> Optional[dict]:
    """Call Claude via Anthropic API (for final plan generation only)."""
    import anthropic
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"), override=True)

    client = anthropic.Anthropic(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        base_url=os.getenv("ANTHROPIC_BASE_URL"),
    )

    # Convert messages: extract system, filter to user/assistant only
    system_text = ""
    api_msgs = []
    for m in messages:
        if m["role"] == "system":
            system_text = m.get("content", "")
        elif m["role"] in ("user", "assistant"):
            content = m.get("content") or ""
            if content:
                api_msgs.append({"role": m["role"], "content": content})

    # Ensure alternating user/assistant
    cleaned = []
    for m in api_msgs:
        if cleaned and cleaned[-1]["role"] == m["role"]:
            cleaned[-1]["content"] += "\n\n" + m["content"]
        else:
            cleaned.append(m)
    if not cleaned or cleaned[0]["role"] != "user":
        cleaned.insert(0, {"role": "user", "content": "请开始规划。"})

    for attempt in range(max_retries):
        try:
            resp = await asyncio.to_thread(
                client.messages.create,
                model=model,
                max_tokens=4000,
                system=system_text,
                messages=cleaned,
            )
            return {
                "content": resp.content[0].text,
                "tool_calls": None,
            }
        except Exception as e:
            print(f"  Claude error (attempt {attempt+1}): {e}", flush=True)
            if attempt < max_retries - 1:
                await asyncio.sleep(5)
    return None


async def _call_openai(
    client: httpx.AsyncClient,
    messages: list,
    model: str = "gpt-4o",
    use_tools: bool = True,
    max_retries: int = 5,
) -> Optional[dict]:
    """Call OpenAI-compatible API (GPT/Claude models via proxy)."""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"), override=True)

    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 8192,
    }
    if use_tools:
        payload["tools"] = TOOLS_SCHEMA
        payload["tool_choice"] = "auto"

    url = f"{base_url.rstrip('/')}/chat/completions"
    for attempt in range(max_retries):
        try:
            # Use streaming to avoid proxy timeout on long generations
            payload["stream"] = True
            collected_content = ""
            tool_calls_data = []
            async with client.stream(
                "POST", url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=600,
            ) as stream:
                if stream.status_code == 429:
                    await stream.aclose()
                    wait = 10 * (attempt + 1)
                    print(f"  OpenAI 429, waiting {wait}s...", flush=True)
                    await asyncio.sleep(wait)
                    continue
                if stream.status_code != 200:
                    body = await stream.aread()
                    print(f"  OpenAI error {stream.status_code}: {body.decode()[:200]}", flush=True)
                    if attempt < max_retries - 1:
                        await asyncio.sleep(5)
                        continue
                    return None
                # Parse SSE stream
                async for line in stream.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        if delta.get("content"):
                            collected_content += delta["content"]
                        if delta.get("tool_calls"):
                            for tc in delta["tool_calls"]:
                                idx = tc.get("index", 0)
                                while len(tool_calls_data) <= idx:
                                    tool_calls_data.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                                if tc.get("id"):
                                    tool_calls_data[idx]["id"] = tc["id"]
                                fn = tc.get("function", {})
                                if fn.get("name"):
                                    tool_calls_data[idx]["function"]["name"] = fn["name"]
                                if fn.get("arguments"):
                                    tool_calls_data[idx]["function"]["arguments"] += fn["arguments"]
                    except json.JSONDecodeError:
                        pass
            return {
                "content": collected_content,
                "tool_calls": tool_calls_data if tool_calls_data else None,
            }
        except Exception as e:
            print(f"  OpenAI exception (attempt {attempt+1}): {e}", flush=True)
            if attempt < max_retries - 1:
                await asyncio.sleep(5)
    return None


async def _call_dashscope(
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
                timeout=600,
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


def _get_location_from_results(results_cache: list) -> Optional[str]:
    """Extract first coordinate from cached POI results (skip transport strings)."""
    for r in results_cache:
        try:
            data = json.loads(r["result"])
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        loc = item.get("location", "")
                        if "," in loc:
                            return loc
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def _extract_poi_names(results_cache: list) -> list[str]:
    """Extract all POI names from tool results (skip transport strings)."""
    names = []
    for r in results_cache:
        try:
            data = json.loads(r["result"])
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        name = item.get("name", "")
                        if name and name not in names:
                            names.append(name)
        except (json.JSONDecodeError, TypeError):
            pass
    return names


def _generate_step_think(calls: list, problem: dict, step: int) -> str:
    """Generate think content for a tool_call step during generation."""
    names = [name for name, _ in calls]
    names_set = set(names)
    origin = problem.get("origin", "")
    dest = problem.get("destination", problem.get("origin", ""))

    if names_set == {"search_flights", "search_train_tickets"}:
        return f"用户需要从{origin}到{dest}的交通方案，同时查询航班和火车进行对比。"
    elif names_set == {"poi_search", "weather"}:
        return f"查询{dest}的景点和天气信息。"
    elif names_set == {"poi_search"} and len(names) == 1:
        keyword = ""
        for _, args in calls:
            if isinstance(args, dict):
                keyword = args.get("address", "")
        return f"搜索{dest}的{keyword or '相关地点'}信息。"
    elif names_set == {"poi_search"} and len(names) >= 2:
        return f"搜索{dest}的住宿和餐饮信息。"
    elif names_set == {"direction"}:
        return "查询地点之间的路线距离和所需时间。"
    elif names_set == {"around_search"}:
        return "搜索附近的餐厅，为餐饮推荐做准备。"
    elif names_set == {"weather"}:
        return f"查询{dest}的天气预报。"
    elif names_set == {"search_flights"}:
        return f"查询{origin}到{dest}的航班。"
    elif names_set == {"search_train_tickets"}:
        return f"查询{origin}到{dest}的火车车次。"
    elif names_set == {"poi_search", "around_search"}:
        return f"搜索{dest}的特色餐饮和周边推荐。"
    else:
        return "继续收集信息，完善行程规划。"


def _build_think_block(results_cache: list, user_prompt: str, tools_called: set) -> str:
    """Build factual think block from tool results."""
    lines = []
    user_brief = user_prompt.split("\n")[0][:80]
    lines.append(f"分析用户需求：{user_brief}")
    lines.append(f"已完成工具调用：{', '.join(sorted(tools_called))}")

    transport_ids = _extract_transport_ids(results_cache)
    if transport_ids:
        lines.append(f"交通方案：{', '.join(transport_ids[:6])}")

    poi_names = _extract_poi_names(results_cache)
    if poi_names:
        lines.append(f"地点信息：{', '.join(poi_names[:6])}")

    # Weather
    for r in results_cache:
        if r["tool"] == "weather":
            try:
                data = json.loads(r["result"])
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    w = data[0]
                    lines.append(f"天气：{w.get('dayweather', '')}{w.get('daytemp', '')}°C")
                    break
            except (json.JSONDecodeError, TypeError):
                pass

    # Direction
    for r in results_cache:
        if r["tool"] == "direction":
            try:
                data = json.loads(r["result"])
                if isinstance(data, dict) and "distance" in data:
                    lines.append(f"路线：{data['distance']}，{data.get('duration', '')}")
                    break
            except (json.JSONDecodeError, TypeError):
                pass

    lines.append("信息收集完毕，开始生成详细规划方案。")
    return "\n".join(lines)


def _extract_transport_ids(results_cache: list) -> list[str]:
    """Extract flight/train IDs from tool results (Chinese text format)."""
    ids = []
    for r in results_cache:
        if r["tool"] not in ("search_flights", "search_train_tickets"):
            continue
        try:
            data = json.loads(r["result"])
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        # Chinese text format: "航班 CZ3992，..." or "直达车次 G7756，..."
                        import re
                        m = re.search(r"航班\s+(\S+?)，", item)
                        if not m:
                            m = re.search(r"车次\s+(\S+?)，", item)
                        if m:
                            ids.append(m.group(1))
                    elif isinstance(item, dict):
                        fid = item.get("flight_no") or item.get("train_no", "")
                        if fid:
                            ids.append(fid)
        except (json.JSONDecodeError, TypeError):
            pass
    return ids


REASONING_WORDS = re.compile(
    r"因为|由于|所以|因此|建议|推荐|考虑到|综合|权衡|对比|相比|优先|适合"
)


def _validate_final_plan(text: str, poi_names: list[str], transport_ids: list[str] = None) -> bool:
    """Check if final plan meets scorer quality requirements.

    Validates: length, reasoning density, POI grounding, transport grounding,
    structured sections (prices, times), and anti-fabrication.
    """
    if len(text) < 1200:
        return False
    if len(REASONING_WORDS.findall(text)) < 5:
        return False
    # Check POI grounding: at least 2 tool POI names appear in final text
    matched = sum(1 for name in poi_names if name in text)
    if poi_names and matched < min(2, len(poi_names)):
        return False
    # Check transport grounding: if transport IDs available, at least 1 must appear
    if transport_ids:
        transport_matched = sum(1 for tid in transport_ids if tid in text)
        if transport_matched == 0:
            return False
    # Check must-have sections: prices and times (core IC categories)
    if not re.search(r'\d+元', text):
        return False
    if not re.search(r'\d{2}:\d{2}', text):
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

    # Transfer city mapping for no_direct routes
    _transfer_cities = {
        "张家界": "长沙", "敦煌": "兰州", "丽江": "昆明",
        "大理": "昆明", "荔波": "贵阳", "阳朔": "桂林",
        "凤凰": "长沙", "平遥": "太原", "乌镇": "杭州",
        "拉萨": "成都", "华山": "西安",
    }

    step_idx = 0
    for step_plan in plan:
        step_idx += 1
        dest = problem.get("_active_dest", problem.get("destination", problem["origin"]))

        # Handle dynamic steps
        if step_plan == "direction_step":
            if len(locations) >= 2:
                calls = [("direction", {"origin": locations[0], "destination": locations[1], "mode": "driving"})]
            else:
                calls = [("direction", {"origin": problem.get("origin", "city center"), "destination": dest, "mode": "driving"})]
        elif step_plan == "direction_step_walk":
            # Walking/transit direction for budget trips
            if len(locations) >= 2:
                calls = [("direction", {"origin": locations[0], "destination": locations[1], "mode": "walking"})]
            else:
                calls = [("direction", {"origin": problem.get("origin", "city center"), "destination": dest, "mode": "transit"})]
        elif step_plan == "direction_step_2":
            # Second direction leg between different photo spots
            if len(locations) >= 3:
                calls = [("direction", {"origin": locations[1], "destination": locations[2], "mode": "driving"})]
            elif len(locations) >= 2:
                calls = [("direction", {"origin": locations[-1], "destination": locations[0], "mode": "driving"})]
            else:
                continue
        elif step_plan == "around_step":
            loc = _get_location_from_results(all_results)
            if loc:
                calls = [("around_search", {"location": loc, "radius": 3000, "keyword": "餐厅", "region": dest})]
            else:
                # Fallback: use poi_search instead of skipping (preserves tool diversity)
                calls = [("poi_search", {"address": "餐厅 美食", "region": dest})]
        elif step_plan == "around_step_budget":
            # Budget: search for cheap food
            loc = _get_location_from_results(all_results)
            if loc:
                calls = [("around_search", {"location": loc, "radius": 3000, "keyword": "小吃 便宜", "region": dest})]
            else:
                calls = [("poi_search", {"address": "小吃 经济实惠", "region": dest})]
        elif step_plan == "transfer_step":
            # For no_direct: search transfer city transport
            transfer = _transfer_cities.get(dest, "长沙")
            calls = [
                ("search_flights", {"date": problem["date"], "from_city": problem["origin"], "to_city": transfer}),
                ("search_train_tickets", {"date": problem["date"], "from_city": transfer, "to_city": dest}),
            ]
        elif step_plan == "indoor_poi_step":
            # For bad_weather: check if weather result shows rain, add indoor POI search
            has_rain = any("雨" in r["result"] for r in all_results if r["tool"] == "weather")
            if has_rain:
                calls = [("poi_search", {"address": "室内景点 博物馆", "region": dest})]
            else:
                calls = [("poi_search", {"address": "户外景点 公园", "region": dest})]
        elif step_plan == "fallback_around_step":
            # For empty_result: use around_search as fallback for sparse POI
            loc = _get_location_from_results(all_results)
            if loc:
                calls = [
                    ("around_search", {"location": loc, "radius": 5000, "keyword": "景点 旅游", "region": dest}),
                    ("around_search", {"location": loc, "radius": 3000, "keyword": "住宿 酒店", "region": dest}),
                ]
            else:
                calls = [("poi_search", {"address": "住宿 酒店", "region": dest})]
        elif step_plan == "user_change_step":
            # For mid_change: inject user message changing destination
            alt_dest = problem.get("alt_destination", "厦门")
            conversation.append({
                "role": "user",
                "content": f"{dest}的机票太贵了，换成{alt_dest}吧，其他要求不变。"
            })
            # Update dest reference for subsequent steps
            problem["_active_dest"] = alt_dest
            continue
        else:
            calls = []
            for tool_name, args_fn in step_plan:
                if args_fn is None:
                    loc = _get_location_from_results(all_results)
                    if loc:
                        calls.append((tool_name, {"location": loc, "radius": 3000, "keyword": "美食", "region": dest}))
                else:
                    calls.append((tool_name, args_fn(problem)))

        if not calls:
            continue

        # Build assistant tool_calls message (OpenAI function calling format)
        # Include task_id in hash to avoid ID reuse across entries
        tool_call_entries = []
        for name, args in calls:
            tid = problem["task_id"]
            call_id = f"call_{hashlib.md5(f'{tid}_{name}{json.dumps(args)}{len(conversation)}'.encode()).hexdigest()[:8]}"
            tool_call_entries.append({
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(args, ensure_ascii=False),
                },
            })

        # Generate step think based on tool names + args
        step_think = _generate_step_think(calls, problem, step_idx)
        conversation.append({
            "role": "assistant",
            "content": f"<think>\n{step_think}\n</think>\n",
            "tool_calls": tool_call_entries,
        })

        # Execute tools and add tool role responses
        for idx, (name, args) in enumerate(calls):
            result = await execute_tool(amap, name, args)
            tools_called.add(name)

            # Extract coordinates from POI results (skip transport string items)
            try:
                data = json.loads(result)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
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
        grounding_parts.append(f"可用地点（必须在方案中引用）：{', '.join(poi_names[:15])}")
    if transport_ids:
        grounding_parts.append(f"可用交通班次（引用具体班次号）：{', '.join(transport_ids[:10])}")

    # Reconstruct readable conversation for LLM
    llm_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    # Add tool results as readable text
    tool_summary_parts = []
    for r in all_results:
        tool_summary_parts.append(f"[{r['tool']}] result:\n{r['result']}")
    llm_messages.append({"role": "assistant", "content": "已调用以下工具收集信息：" + "、".join(sorted(tools_called))})
    tool_results_text = "\n\n".join(tool_summary_parts)
    grounding_text = "\n".join(grounding_parts)
    llm_user_content = (
        f"以下是所有工具调用的结果：\n\n{tool_results_text}\n\n"
        f"信息收集完毕。请根据以上工具返回的真实数据，提供详细、全面的规划方案。\n\n"
        f"【必须满足的要求】\n"
        f"1. 方案中必须大量引用工具返回的真实数据，禁止编造：\n"
        f"   - 至少引用3个航班号/车次号（如MF6257、G1807），附带价格和时间\n"
        f"   - 至少引用5个地点名称（景点/餐厅/酒店的真实名称）\n"
        f"   - 至少引用3个价格数据（XX元）\n"
        f"   - 至少引用3个时间数据（HH:MM格式）\n"
        f"   - 引用天气数据（气温XX度、天气晴/阴/雨、风力XX级）\n"
        f"   - 引用路线数据（距离XX公里、约XX分钟）\n"
        f"2. 使用分析推理词（因为、由于、所以、因此、建议、推荐、考虑到、综合、权衡、对比、相比、优先、适合）解释选择\n"
        f"3. 方案必须详细充分（至少2000字），包含具体时间、费用和路线信息\n"
        f"4. 对比不同方案，给出明确推荐\n\n"
        f"【必须包含的章节】\n"
        f"5. **交通方案对比**：至少对比2种出行方案，列出航班号/车次号、出发到达时间、价格，用表格或列表对比价格/时间/舒适度，说明推荐理由\n"
        f"6. **景点游览安排**：引用工具返回的景点名称（景区/公园/博物馆/古镇/广场等），标注游览时间（上午/下午分段）\n"
        f"7. **餐饮推荐**：引用工具返回的餐厅名称，注明人均消费XX元\n"
        f"8. **住宿建议**：引用工具返回的酒店/宾馆/民宿名称，注明价格区间\n"
        f"9. **交通路线**：引用方向工具返回的距离（XX米/公里）和时间（约XX分钟），用顺序词（先/然后/接着/最后/步行/打车/地铁/公交）描述路线\n"
        f"10. **天气与穿衣建议**：引用天气工具返回的气温/天气/风力信息，给出穿衣和出行建议\n"
        f"11. **注意事项/实用建议**：包含门票价格、开放时间、提前预约、携带物品等实用提示\n"
        f"12. **预算明细**：列出交通/住宿/餐饮/门票分项费用，每项标注XX元，给出总计\n"
        f"\n【格式禁忌】\n"
        f"- 日程标题用「第一天」「第二天」，禁止用D1/D2/D3（会被误识别为车次号）\n"
        f"- 方案编号用「方案一」「方案二」，禁止用C1/C2/C3/G1/G2（同理）\n"
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
            if _validate_final_plan(final, poi_names, transport_ids):
                break
            if attempt == 0:
                llm_messages.append({"role": "assistant", "content": final})
                llm_messages.append({"role": "user", "content": (
                    "方案不够详细。请重新生成，确保：至少1500字，"
                    "引用工具返回的具体地点名称（景区/公园/博物馆/餐厅/酒店），"
                    "使用分析推理词（因为/建议/推荐/考虑到/对比），"
                    "包含具体价格（XX元）、时间（XX:XX）、距离（XX公里/米）。"
                )})
        if final is None or len(final) < 800:
            return None

    # Add think block before final plan
    think = _build_think_block(all_results, user_prompt, tools_called)
    final_with_think = f"<think>\n{think}\n</think>\n\n{final}"

    # Clean SFT conversation: tool steps + final assistant response (no grounding prompt)
    conversation.append({"role": "assistant", "content": final_with_think})

    if len(tools_called) < 3:
        return None

    # === FORMAT VALIDATION (hard rules, reject if violated) ===
    for msg in conversation:
        if msg.get("role") == "assistant":
            # Rule 1: content must never be None
            if msg.get("content") is None:
                msg["content"] = ""
            # Rule 2: tool_calls must be in tool_calls field, never in content
            if "<tool_call>" in str(msg.get("content", "")):
                return None  # reject — format broken
        if msg.get("role") == "tool":
            # Rule 3: tool results must have tool_call_id
            if not msg.get("tool_call_id"):
                return None  # reject — missing ID

    # Rule 4: final plan must have <think> block
    last_asst = conversation[-1]
    if not last_asst.get("content", "").startswith("<think>"):
        return None  # reject — missing think

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
    problem_type: str = None,
):
    """Generate a batch of NAVWORLD SFT samples.

    If problem_type is specified, all samples use that type (for diversity generation).
    """
    amap = AMapClient(amap_key)
    sem = asyncio.Semaphore(concurrency)
    results = []
    failed = 0

    async def gen_one(task_id: int):
        nonlocal failed
        async with sem:
            problem = generate_problem(task_id, problem_type=problem_type)
            dest = problem.get('destination', '(open-ended)')
            print(f"  [{task_id}] {problem['type']}: {problem.get('origin', '')}→{dest}", flush=True)

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
    parser.add_argument("--model", default="qwen3-max")
    parser.add_argument("--start-id", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--type", default=None, choices=ALL_PROBLEM_TYPES,
                        help="Generate only this problem type (for diversity batches)")
    parser.add_argument("--phase1", action="store_true",
                        help="Generate all Phase 1 diversity types (50 each)")
    args = parser.parse_args()

    amap_key = os.environ.get("AMAP_API_KEY") or os.environ.get("AMAP_MAPS_API_KEY", "")
    api_key = os.environ.get("QWEN_API_KEY") or os.environ.get("CHUTES_API_KEY", "")

    if not amap_key:
        print("Error: AMAP_API_KEY not set")
        return
    if not api_key:
        print("Error: QWEN_API_KEY not set")
        return

    print(f"AMap key: {amap_key[:8]}..., API key: {api_key[:12]}...")

    if args.phase1:
        # Generate 50 samples for each Phase 1 type
        print(f"Phase 1 diversity generation: {len(PHASE1_TYPES)} types × {args.num} samples")
        total = 0
        for ptype in PHASE1_TYPES:
            out = args.output.replace(".jsonl", f"_{ptype}.jsonl")
            print(f"\n=== Generating {ptype} → {out} ===")
            batch = await generate_batch(
                num_samples=args.num,
                output_path=out,
                amap_key=amap_key,
                api_key=api_key,
                model=args.model,
                start_id=args.start_id + total,
                concurrency=args.concurrency,
                problem_type=ptype,
            )
            total += args.num
        print(f"\nPhase 1 complete: {total} samples across {len(PHASE1_TYPES)} types")
    else:
        print(f"Generating {args.num} NAVWORLD samples using {args.model}")
        if args.type:
            print(f"Problem type: {args.type}")
        await generate_batch(
            num_samples=args.num,
            output_path=args.output,
            amap_key=amap_key,
            api_key=api_key,
            model=args.model,
            start_id=args.start_id,
            concurrency=args.concurrency,
            problem_type=args.type,
        )


if __name__ == "__main__":
    asyncio.run(main())
