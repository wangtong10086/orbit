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
from forge.data.navworld_prompts import (
    SYSTEM_PROMPT,
    TOOLS_SCHEMA,
    generate_problem,
    problem_to_prompt,
)


# ============================================================================
# LLM client (DashScope)
# ============================================================================

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
