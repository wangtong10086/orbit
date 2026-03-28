#!/usr/bin/env python3
"""Convert OpenAI tool_calls format to ms-swift agent format.

Runs automatically before training. Data producers keep using OpenAI standard format.

OpenAI format (input):
  {"role": "assistant", "content": null, "tool_calls": [{"id":"call_1","type":"function","function":{"name":"search","arguments":"{...}"}}]}
  {"role": "tool", "content": "result", "tool_call_id": "call_1"}

ms-swift format (output):
  {"role": "tool_call", "content": "{\"name\":\"search\",\"arguments\":{...}}"}
  {"role": "tool_response", "content": "result"}

Usage:
  python3 convert_openai_to_msswift.py --input combined.jsonl --output combined_msswift.jsonl
"""

import argparse
import json
import random
import sys


def convert_message(msg):
    """Convert a single message from OpenAI to ms-swift format."""
    role = msg.get("role")
    content = msg.get("content")
    tool_calls = msg.get("tool_calls")

    # assistant with tool_calls → split into tool_call messages + optional assistant
    if role == "assistant" and tool_calls:
        results = []
        # If assistant has content AND tool_calls, emit content as assistant first
        if content and content.strip():
            results.append({"role": "assistant", "content": content})
        # Each tool_call becomes a separate tool_call message
        for tc in tool_calls:
            func = tc.get("function", {})
            tc_content = {
                "name": func.get("name", ""),
                "arguments": func.get("arguments", "{}"),
            }
            # If arguments is a string, try to parse it
            if isinstance(tc_content["arguments"], str):
                try:
                    tc_content["arguments"] = json.loads(tc_content["arguments"])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append({
                "role": "tool_call",
                "content": json.dumps(tc_content, ensure_ascii=False),
            })
        return results

    # tool → tool_response
    if role == "tool":
        return [{"role": "tool_response", "content": content or ""}]

    # Regular messages (system, user, assistant without tool_calls)
    # Ensure content is not None
    if content is None:
        content = ""
    return [{"role": role, "content": content}]


def convert_sample(sample):
    """Convert one training sample from OpenAI to ms-swift format."""
    messages = sample.get("messages", [])
    tools = sample.get("tools")

    new_messages = []
    for msg in messages:
        new_messages.extend(convert_message(msg))

    result = {"messages": new_messages}

    # tools: ms-swift expects JSON string, not list
    if tools:
        if isinstance(tools, list):
            result["tools"] = json.dumps(tools, ensure_ascii=False)
        elif isinstance(tools, str):
            result["tools"] = tools

    return result


def main():
    parser = argparse.ArgumentParser(description="Convert OpenAI tool_calls to ms-swift format")
    parser.add_argument("--input", required=True, help="Input JSONL (OpenAI format)")
    parser.add_argument("--output", required=True, help="Output JSONL (ms-swift format)")
    parser.add_argument("--shuffle", action="store_true", default=True, help="Shuffle output (default: True)")
    parser.add_argument("--no-shuffle", action="store_false", dest="shuffle")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for shuffle")
    parser.add_argument("--stats", action="store_true", default=True, help="Print conversion stats")
    args = parser.parse_args()

    data = []
    stats = {
        "total": 0,
        "converted_tool_calls": 0,
        "converted_tool_response": 0,
        "passthrough": 0,
        "tools_stringified": 0,
    }

    with open(args.input) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            sample = json.loads(line)
            stats["total"] += 1

            # Count conversions
            for msg in sample.get("messages", []):
                if msg.get("role") == "assistant" and msg.get("tool_calls"):
                    stats["converted_tool_calls"] += 1
                elif msg.get("role") == "tool":
                    stats["converted_tool_response"] += 1

            if sample.get("tools") and isinstance(sample["tools"], list):
                stats["tools_stringified"] += 1

            converted = convert_sample(sample)
            data.append(converted)

    stats["passthrough"] = stats["total"] - stats["converted_tool_calls"] - stats["tools_stringified"]

    if args.shuffle:
        random.seed(args.seed)
        random.shuffle(data)

    with open(args.output, "w") as f:
        for d in data:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    if args.stats:
        print(f"Converted: {stats['total']} samples")
        print(f"  tool_calls → tool_call role: {stats['converted_tool_calls']} messages")
        print(f"  tool → tool_response:        {stats['converted_tool_response']} messages")
        print(f"  tools list → JSON string:    {stats['tools_stringified']} samples")
        print(f"  Shuffled: {args.shuffle}")
        print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
