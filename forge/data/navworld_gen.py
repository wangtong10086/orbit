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
    """Check if model is an OpenAI/GPT model (use OpenAI-compatible API)."""
    return "gpt" in model.lower() or "o1" in model.lower() or "o3" in model.lower()


async def call_llm(
    client: httpx.AsyncClient,
    messages: list,
    api_key: str,
    model: str = "qwen3-max",
    use_tools: bool = True,
    max_retries: int = 3,
) -> Optional[dict]:
    """Call LLM via DashScope or Anthropic API."""
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
    max_retries: int = 3,
) -> Optional[dict]:
    """Call OpenAI-compatible API (GPT models)."""
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
            r = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=180,
            )
            if r.status_code == 429:
                wait = 10 * (attempt + 1)
                print(f"  OpenAI 429, waiting {wait}s...", flush=True)
                await asyncio.sleep(wait)
                continue
            if r.status_code != 200:
                print(f"  OpenAI error {r.status_code}: {r.text[:200]}", flush=True)
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
                    continue
                return None
            data = r.json()
            choice = data.get("choices", [{}])[0]
            msg = choice.get("message", {})
            return {
                "content": msg.get("content", ""),
                "tool_calls": msg.get("tool_calls"),
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
                continue
        elif step_plan == "around_step_budget":
            # Budget: search for cheap food
            loc = _get_location_from_results(all_results)
            if loc:
                calls = [("around_search", {"location": loc, "radius": 3000, "keyword": "小吃 便宜", "region": dest})]
            else:
                continue
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
