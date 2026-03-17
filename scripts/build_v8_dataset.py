#!/usr/bin/env python3
"""Build v8 training dataset: use Qwen3 tokenizer.apply_chat_template to correctly handle all formats.

Key improvements vs v7:
- NAVWORLD/LIVEWEB: preserve native tool_calls/tool/tool_call_id, process with apply_chat_template(tools=)
- GAME: keep messages-only format
- SWE-SYNTH: keep messages-only format
- Output is a text field (already templated), not a messages field
"""

import json
import sys
from pathlib import Path
from transformers import AutoTokenizer

def load_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f]

def has_tool_calls(messages):
    """Check if any message has tool_calls or role=tool."""
    for m in messages:
        if 'tool_calls' in m or m.get('role') == 'tool':
            return True
    return False

def extract_tools_from_system(messages):
    """Extract tools definition from NAVWORLD/LIVEWEB system prompt."""
    # NAVWORLD tools schema
    navworld_tools = [
        {"type": "function", "function": {"name": "poi_search", "description": "Search for POI (attractions, hotels, restaurants, etc.).", "parameters": {"type": "object", "properties": {"address": {"type": "string", "description": "Search keyword or address"}, "region": {"type": "string", "description": "City name"}}, "required": ["address"]}}},
        {"type": "function", "function": {"name": "around_search", "description": "Search nearby facilities", "parameters": {"type": "object", "properties": {"location": {"type": "string", "description": "Center coordinates"}, "radius": {"type": "integer"}, "keyword": {"type": "string"}, "region": {"type": "string"}}, "required": ["location"]}}},
        {"type": "function", "function": {"name": "direction", "description": "Route planning", "parameters": {"type": "object", "properties": {"origin": {"type": "string"}, "destination": {"type": "string"}, "mode": {"type": "string"}}, "required": ["origin", "destination"]}}},
        {"type": "function", "function": {"name": "weather", "description": "Weather query", "parameters": {"type": "object", "properties": {"city": {"type": "string", "description": "City name"}}, "required": ["city"]}}},
        {"type": "function", "function": {"name": "search_flights", "description": "Flight search", "parameters": {"type": "object", "properties": {"date": {"type": "string"}, "from_city": {"type": "string"}, "to_city": {"type": "string"}}, "required": ["date", "from_city", "to_city"]}}},
        {"type": "function", "function": {"name": "search_train_tickets", "description": "Train ticket search", "parameters": {"type": "object", "properties": {"date": {"type": "string"}, "from_city": {"type": "string"}, "to_city": {"type": "string"}}, "required": ["date", "from_city", "to_city"]}}},
    ]
    return navworld_tools

def process_tool_calling_data(records, tokenizer, env_name):
    """Process data with tool_calls using apply_chat_template."""
    results = []
    errors = 0
    tools = extract_tools_from_system(None) if env_name == "NAVWORLD" else None

    for i, record in enumerate(records):
        msgs = record['messages']
        try:
            text = tokenizer.apply_chat_template(
                msgs, tools=tools, tokenize=False, add_generation_prompt=False
            )
            results.append({"text": text})
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"  [{env_name}] Error #{errors} at record {i}: {e}")

    return results, errors

def process_plain_data(records, tokenizer):
    """Process plain messages data (GAME, SWE-SYNTH) using apply_chat_template."""
    results = []
    errors = 0

    for i, record in enumerate(records):
        msgs = record['messages']
        # Strip any non-standard fields from messages
        clean_msgs = []
        for m in msgs:
            clean = {"role": m["role"], "content": m.get("content", "")}
            clean_msgs.append(clean)

        try:
            text = tokenizer.apply_chat_template(
                clean_msgs, tokenize=False, add_generation_prompt=False
            )
            results.append({"text": text})
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"  Error #{errors} at record {i}: {e}")

    return results, errors

def main():
    print("Loading Qwen3 tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-32B", trust_remote_code=True)

    datasets = {
        # GAME data
        "GAME_v7": "data/game_v7_clean.jsonl",
        "GAME_bot_goofspiel": "data/game_bot_goofspiel.jsonl",
        "GAME_bot_leduc": "data/game_bot_leduc_poker.jsonl",
        "GAME_bot_liars": "data/game_bot_liars_dice.jsonl",
        "GAME_bot_gin": "data/game_bot_gin_rummy.jsonl",
        "GAME_bot_othello": "data/game_bot_othello.jsonl",
        "GAME_bot_hex": "data/game_bot_hex.jsonl",
        "GAME_bot_clobber": "data/game_bot_clobber.jsonl",
        # NAVWORLD - needs tool calling format (v9 merged = 2153 entries, 100% direction, new API key)
        "NAVWORLD_v9_merged": "data/navworld_v9_merged.jsonl",
        # SWE-SYNTH
        "SWE-SYNTH": "data/swe-synth_v7_clean.jsonl",
        # LIVEWEB
        "LIVEWEB": "data/liveweb_v7_clean.jsonl",
        # LGC-v2 / PRINT (still scored on leaderboard)
        "LGC-v2": "data/lgc-v2_sft.jsonl",
        "PRINT": "data/print_sft.jsonl",
    }

    all_records = []

    for name, path in datasets.items():
        if not Path(path).exists():
            print(f"  SKIP {name}: {path} not found")
            continue

        records = load_jsonl(path)
        print(f"\n{name}: {len(records)} records from {path}")

        if has_tool_calls(records[0]['messages']) if records else False:
            # Tool calling data (NAVWORLD, LIVEWEB)
            env = "NAVWORLD" if "NAVWORLD" in name else "LIVEWEB"
            processed, errors = process_tool_calling_data(records, tokenizer, env)
            print(f"  Processed with tool_calls: {len(processed)} ok, {errors} errors")
        else:
            # Plain messages data (GAME, SWE-SYNTH)
            processed, errors = process_plain_data(records, tokenizer)
            print(f"  Processed plain: {len(processed)} ok, {errors} errors")

        all_records.extend(processed)

    # Write output
    output = "data/v11_mixed_sft.jsonl"
    with open(output, "w") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n{'='*60}")
    print(f"v8 dataset: {len(all_records)} records -> {output}")
    print(f"Format: text field (apply_chat_template output)")

if __name__ == "__main__":
    main()
