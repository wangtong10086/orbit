"""Add <think> blocks to NAVWORLD canonical data and fix tool_call format.

Two fixes:
1. Add think block before final plan (last assistant message)
2. Convert <tool_call> in content to standard tool_calls field
"""

import json
import re
import hashlib
from pathlib import Path


def extract_think_content(msgs: list, user_prompt: str) -> str:
    """Generate think content from tool results — factual summary only."""
    tools_used = []
    poi_names = []
    transport_ids = []
    weather_info = []
    direction_info = []

    for msg in msgs:
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {}).get("name", "")
                if fn:
                    tools_used.append(fn)

        if msg.get("role") == "tool":
            content = msg.get("content", "")
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            if "name" in item:
                                poi_names.append(item["name"])
                            if "dayweather" in item:
                                weather_info.append(f"{item.get('dayweather', '')}{item.get('daytemp', '')}°C")
                        elif isinstance(item, str):
                            # Transport strings
                            ids = re.findall(r"[A-Z]{1,3}\d{3,5}", item)
                            transport_ids.extend(ids)
                elif isinstance(data, dict):
                    if "distance" in data:
                        direction_info.append(f"{data['distance']}，{data.get('duration', '')}")
            except (json.JSONDecodeError, TypeError):
                pass

    # Build think
    lines = []

    # User need summary (first 60 chars of user prompt, clean)
    user_brief = user_prompt.split("\n")[0][:80]
    lines.append(f"分析用户需求：{user_brief}")

    # Tools called
    unique_tools = list(dict.fromkeys(tools_used))
    lines.append(f"已完成工具调用：{', '.join(unique_tools)}")

    # Key data collected
    if transport_ids:
        lines.append(f"交通方案：{', '.join(transport_ids[:6])}")
    if poi_names:
        lines.append(f"地点信息：{', '.join(poi_names[:6])}")
    if weather_info:
        lines.append(f"天气：{', '.join(weather_info[:2])}")
    if direction_info:
        lines.append(f"路线：{', '.join(direction_info[:2])}")

    lines.append("信息收集完毕，开始生成详细规划方案。")

    return "\n".join(lines)


def fix_content_tool_calls(msg: dict) -> dict:
    """Convert <tool_call> in content to standard tool_calls field."""
    content = msg.get("content", "")
    if "<tool_call>" not in content:
        return msg

    # Parse all <tool_call> blocks
    pattern = r"<tool_call>\s*(\{.*?\})\s*</tool_call>"
    matches = re.findall(pattern, content, re.DOTALL)

    if not matches:
        return msg

    tool_calls = []
    for m in matches:
        try:
            tc_data = json.loads(m)
            name = tc_data.get("name", "")
            args = tc_data.get("arguments", {})
            if isinstance(args, dict):
                args = json.dumps(args, ensure_ascii=False)
            # Generate stable call_id
            call_id = f"call_{hashlib.md5(f'{name}{args}'.encode()).hexdigest()[:8]}"
            tool_calls.append({
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": args,
                },
            })
        except json.JSONDecodeError:
            continue

    if tool_calls:
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": tool_calls,
        }
    return msg


def process_entry(entry: dict) -> dict:
    """Process one entry: fix format + add think."""
    msgs = entry["messages"]

    # Step 1: Fix <tool_call> in content → standard tool_calls
    new_msgs = []
    for msg in msgs:
        if msg.get("role") == "assistant" and "<tool_call>" in str(msg.get("content", "")):
            new_msgs.append(fix_content_tool_calls(msg))
        else:
            new_msgs.append(msg)

    # Step 2: Add think block before final plan
    # Find last assistant message without tool_calls (the plan)
    plan_idx = None
    for i in range(len(new_msgs) - 1, -1, -1):
        if (new_msgs[i].get("role") == "assistant"
                and new_msgs[i].get("content")
                and not new_msgs[i].get("tool_calls")
                and "<tool_call>" not in new_msgs[i].get("content", "")):
            plan_idx = i
            break

    if plan_idx is not None:
        plan_content = new_msgs[plan_idx]["content"]
        # Don't double-add think
        if not plan_content.startswith("<think>"):
            # Get user prompt
            user_prompt = ""
            for msg in new_msgs:
                if msg.get("role") == "user":
                    user_prompt = msg.get("content", "")
                    break

            think = extract_think_content(new_msgs, user_prompt)
            new_msgs[plan_idx]["content"] = f"<think>\n{think}\n</think>\n\n{plan_content}"

    entry["messages"] = new_msgs
    return entry


def main():
    canonical = Path("data/canonical/navworld.jsonl")

    entries = []
    with open(canonical) as f:
        for line in f:
            entries.append(json.loads(line))

    print(f"Processing {len(entries)} entries...")

    # Count issues before
    fmt2_before = 0
    no_think_before = 0
    for e in entries:
        for msg in e["messages"]:
            if msg.get("role") == "assistant" and "<tool_call>" in str(msg.get("content", "")):
                fmt2_before += 1
                break
        has_think = any("<think>" in str(msg.get("content", "")) for msg in e["messages"] if msg.get("role") == "assistant")
        if not has_think:
            no_think_before += 1

    print(f"Before: format2={fmt2_before}, no_think={no_think_before}")

    # Process
    processed = [process_entry(e) for e in entries]

    # Count after
    fmt2_after = 0
    no_think_after = 0
    for e in processed:
        for msg in e["messages"]:
            if msg.get("role") == "assistant" and "<tool_call>" in str(msg.get("content", "")):
                fmt2_after += 1
                break
        has_think = any("<think>" in str(msg.get("content", "")) for msg in e["messages"] if msg.get("role") == "assistant")
        if not has_think:
            no_think_after += 1

    print(f"After:  format2={fmt2_after}, no_think={no_think_after}")

    # Validate: check a few entries
    for i in [0, 500, 1000, 1500, 1767]:
        e = processed[i]
        msgs = e["messages"]
        plan = ""
        for msg in reversed(msgs):
            if msg.get("role") == "assistant" and msg.get("content") and not msg.get("tool_calls"):
                plan = msg["content"]
                break
        has_think = "<think>" in plan
        has_plan = len(plan) > 500
        tc_ok = all(msg.get("tool_calls") or "<tool_call>" not in str(msg.get("content", ""))
                     for msg in msgs if msg.get("role") == "assistant")
        print(f"  [{i}] think={has_think} plan={has_plan} tc_format_ok={tc_ok} plan_len={len(plan)}")

    # Write
    with open(canonical, "w") as f:
        for e in processed:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"\nWritten {len(processed)} entries to {canonical}")


if __name__ == "__main__":
    main()
