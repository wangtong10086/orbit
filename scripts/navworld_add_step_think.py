"""Add <think> blocks to every assistant tool_call message in NAVWORLD data.

Strategist directive: sglang --reasoning-parser qwen3 requires <think> in
every assistant message, not just the final plan.

Approach:
- For each tool_call message, generate a short think based on tool names + args
- Extract city/destination from tool arguments (more reliable than user prompt)
- Keep final plan's think unchanged (already has factual summary)
"""

import json
import re
from pathlib import Path


def extract_city_from_args(tool_calls: list) -> tuple[str, str]:
    """Extract origin/destination cities from tool call arguments."""
    origin = ""
    dest = ""
    for tc in tool_calls:
        args = tc.get("function", {}).get("arguments", "{}")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                continue
        if isinstance(args, dict):
            if "from_city" in args and not origin:
                origin = args["from_city"]
            if "to_city" in args and not dest:
                dest = args["to_city"]
            if "region" in args and not dest:
                dest = args["region"]
            if "city" in args and not dest:
                dest = args["city"]
    return origin, dest


def generate_step_think(tool_calls: list, step: int, origin: str, dest: str) -> str:
    """Generate think content for a tool_call step."""
    names = [tc.get("function", {}).get("name", "") for tc in tool_calls]
    names_set = set(names)

    # Extract keyword from poi_search args
    keyword = ""
    for tc in tool_calls:
        fn = tc.get("function", {})
        if fn.get("name") == "poi_search":
            args = fn.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except:
                    pass
            if isinstance(args, dict):
                keyword = args.get("address", "")

    # Generate contextual think
    if names_set == {"search_flights", "search_train_tickets"}:
        if origin and dest:
            return f"用户需要从{origin}到{dest}的交通方案，同时查询航班和火车进行对比。"
        return "查询航班和火车车次，为交通方案对比做准备。"

    elif names_set == {"poi_search", "weather"}:
        return f"查询{dest}的{'景点' if not keyword else keyword}和天气信息。"

    elif names_set == {"poi_search"} and len(names) == 1:
        if keyword:
            return f"搜索{dest}的{keyword}信息。"
        return f"搜索{dest}的相关地点信息。"

    elif names_set == {"poi_search"} and len(names) == 2:
        return f"搜索{dest}的住宿和餐饮信息。"

    elif names_set == {"poi_search", "around_search"}:
        return f"搜索{dest}的特色餐饮和周边推荐。"

    elif names_set == {"direction"}:
        return "查询地点之间的路线距离和所需时间。"

    elif names_set == {"around_search"}:
        return "搜索附近的餐厅，为餐饮推荐做准备。"

    elif names_set == {"weather"}:
        return f"查询{dest}的天气预报。"

    elif names_set == {"search_flights"}:
        if origin and dest:
            return f"查询{origin}到{dest}的航班。"
        return "查询航班信息。"

    elif names_set == {"search_train_tickets"}:
        if origin and dest:
            return f"查询{origin}到{dest}的火车车次。"
        return "查询火车车次信息。"

    else:
        tool_names_cn = {
            "search_flights": "航班",
            "search_train_tickets": "火车",
            "poi_search": "地点",
            "weather": "天气",
            "direction": "路线",
            "around_search": "周边",
        }
        cn_names = [tool_names_cn.get(n, n) for n in names]
        return f"查询{'/'.join(cn_names)}信息。"


def process_entry(entry: dict) -> dict:
    """Add think to every tool_call message."""
    msgs = entry["messages"]

    # First pass: extract origin/dest from all tool args
    origin = ""
    dest = ""
    for msg in msgs:
        if msg.get("tool_calls"):
            o, d = extract_city_from_args(msg["tool_calls"])
            if o and not origin:
                origin = o
            if d and not dest:
                dest = d

    # Second pass: add think to tool_call messages
    step = 0
    for msg in msgs:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            step += 1
            content = msg.get("content", "")

            # Skip if already has think
            if "<think>" in content:
                continue

            think = generate_step_think(msg["tool_calls"], step, origin, dest)
            msg["content"] = f"<think>\n{think}\n</think>\n"

    return entry


def validate_entry(entry: dict) -> list[str]:
    """Validate entry format after modification."""
    issues = []
    msgs = entry["messages"]

    for i, msg in enumerate(msgs):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")

            # Rule 1: content must not be None
            if content is None:
                issues.append(f"msg[{i}]: content is None")

            # Rule 2: no <tool_call> in content
            if "<tool_call>" in str(content):
                issues.append(f"msg[{i}]: <tool_call> in content")

            # Rule 3: tool_call messages must have think
            if msg.get("tool_calls") and "<think>" not in str(content):
                issues.append(f"msg[{i}]: tool_call without think")

            # Rule 4: final plan must have think
            if not msg.get("tool_calls") and content and "<think>" not in str(content):
                issues.append(f"msg[{i}]: plan without think")

        if msg.get("role") == "tool":
            if not msg.get("tool_call_id"):
                issues.append(f"msg[{i}]: tool without tool_call_id")

    return issues


def main():
    canonical = Path("data/canonical/navworld.jsonl")

    entries = []
    with open(canonical) as f:
        for line in f:
            entries.append(json.loads(line))

    print(f"Processing {len(entries)} entries...")

    # Count before
    tc_no_think = sum(
        1 for e in entries for m in e["messages"]
        if m.get("role") == "assistant" and m.get("tool_calls") and "<think>" not in str(m.get("content", ""))
    )
    print(f"Before: {tc_no_think} tool_call messages without think")

    # Process
    processed = [process_entry(e) for e in entries]

    # Validate
    total_issues = 0
    for i, e in enumerate(processed):
        issues = validate_entry(e)
        if issues:
            total_issues += len(issues)
            if total_issues <= 10:
                print(f"Entry {i}: {issues}")

    # Count after
    tc_no_think_after = sum(
        1 for e in processed for m in e["messages"]
        if m.get("role") == "assistant" and m.get("tool_calls") and "<think>" not in str(m.get("content", ""))
    )
    print(f"After: {tc_no_think_after} tool_call messages without think")
    print(f"Validation issues: {total_issues}")

    # tool_call_id missing is a known issue in 221 entries (1429-1652)
    # These were previously format-fixed but tool_call_id wasn't added
    critical_issues = sum(
        1 for e in processed for issue in validate_entry(e)
        if "tool_call_id" not in issue
    )
    if critical_issues > 0:
        print(f"CRITICAL issues (non-tool_call_id): {critical_issues}, NOT writing")
        return

    # Sample check
    for idx in [0, 500, 1500, 2968]:
        e = processed[idx]
        print(f"\n  [{idx}] {e.get('problem_type', '?')}:")
        for j, m in enumerate(e["messages"]):
            if m.get("role") == "assistant" and m.get("tool_calls"):
                content = m["content"]
                think_end = content.index("</think>")
                think = content[8:think_end].strip()
                names = [t["function"]["name"] for t in m["tool_calls"]]
                print(f"    step: {names} → think=\"{think}\"")

    # Write
    with open(canonical, "w") as f:
        for e in processed:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"\nWritten {len(processed)} entries")


if __name__ == "__main__":
    main()
