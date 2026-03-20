#!/usr/bin/env python3
"""
Batch regenerate think blocks in GAME data using GPT-5.4 API.

Approach: batch multiple think translations per API call.
Group thinks by game, send batches of 10-20 thinks per call.

Usage:
    python3 scripts/game_think_regen.py --input data/game_cleaned.jsonl --max-entries 100
    python3 scripts/game_think_regen.py --input data/game_cleaned.jsonl --all
"""

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".pylibs"))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"), override=True)

import httpx

CHINESE_PAT = re.compile(r'[\u4e00-\u9fff]')
THINK_PAT = re.compile(r'<think>(.*?)</think>', re.DOTALL)

LOW_QUALITY_TEMPLATES = {
    "Organize hand, keep cards that form melds, discard highest deadwood.",
    "My dice [], face 1 appears 0 times. Conservative bid, avoid overbidding.",
    "Only one legal action available.",
    "Upcard doesn't improve hand, draw from stock for better chances.",
    "Upcard doesn't help current melds, pass.",
}

API_KEY = os.environ.get("OPENAI_API_KEY", "")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "")
MODEL = "gpt-5.4"
BATCH_SIZE = 15  # thinks per API call


def collect_thinks_to_fix(entries):
    """Collect all think blocks needing fix with their locations."""
    fixes = []
    for i, e in enumerate(entries):
        game = e.get("game", "unknown")
        for j, m in enumerate(e["messages"]):
            if m["role"] != "assistant":
                continue
            match = THINK_PAT.search(m["content"])
            if not match:
                continue
            think = match.group(1).strip()
            action = THINK_PAT.sub("", m["content"]).strip()

            reason = None
            if CHINESE_PAT.search(think):
                reason = "chinese"
            elif think in LOW_QUALITY_TEMPLATES:
                reason = "template"

            if reason:
                # Get context from preceding user message
                context = ""
                if j > 0 and e["messages"][j - 1]["role"] == "user":
                    context = e["messages"][j - 1]["content"][:200]

                fixes.append({
                    "entry_idx": i,
                    "msg_idx": j,
                    "game": game,
                    "think": think,
                    "action": action,
                    "context": context,
                    "reason": reason,
                })

    return fixes


def call_openai_batch(batch):
    """Send a batch of thinks to GPT-5.4 for translation/regeneration."""
    game = batch[0]["game"]

    items = []
    for k, fix in enumerate(batch):
        if fix["reason"] == "chinese":
            items.append(f'{k}. [TRANSLATE] Game={fix["game"]}, Action={fix["action"]}\n   Chinese: {fix["think"][:150]}')
        else:
            items.append(f'{k}. [IMPROVE] Game={fix["game"]}, Action={fix["action"]}\n   Context: {fix["context"][:100]}\n   Current: {fix["think"][:100]}')

    items_text = "\n".join(items)

    prompt = f"""You are improving strategic reasoning for a {game} game AI training dataset.

For each item below, generate a concise English strategic reasoning (1-2 sentences) that:
- Explains WHY the action is strategically good
- Uses {game}-specific terminology
- Is diverse (don't repeat the same phrasing)
- Does NOT mention the action ID number

Items:
{items_text}

Respond as a JSON array of strings, one per item, in order. Example: ["reasoning 1", "reasoning 2", ...]
Output ONLY the JSON array."""

    try:
        resp = httpx.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "max_tokens": 2000,
                "temperature": 0.8,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        return parse_json_array(text)
    except Exception as e:
        print(f"  API error: {e}")
        return None


def parse_json_array(text):
    """Parse JSON array from API response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--max-entries", type=int, default=0, help="Max entries with issues (0=all)")
    parser.add_argument("--max-thinks", type=int, default=0, help="Max thinks to fix (0=all)")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    if args.output is None:
        base = Path(args.input).stem
        args.output = str(Path(args.input).parent / f"{base}_regen.jsonl")

    entries = []
    with open(args.input) as f:
        for line in f:
            entries.append(json.loads(line))
    print(f"Loaded {len(entries)} entries")

    fixes = collect_thinks_to_fix(entries)
    chinese = sum(1 for f in fixes if f["reason"] == "chinese")
    template = sum(1 for f in fixes if f["reason"] == "template")
    print(f"Thinks to fix: {len(fixes)} (chinese={chinese}, template={template})")

    if args.max_thinks > 0:
        fixes = fixes[:args.max_thinks]
        print(f"Limited to first {len(fixes)} thinks")

    if args.dry_run:
        print("[DRY RUN] Exiting.")
        return

    # Create batches grouped by game
    by_game = defaultdict(list)
    for fix in fixes:
        by_game[fix["game"]].append(fix)

    batches = []
    for game, game_fixes in by_game.items():
        for i in range(0, len(game_fixes), args.batch_size):
            batches.append(game_fixes[i:i + args.batch_size])

    print(f"API calls needed: {len(batches)} (batch_size={args.batch_size})")

    # Process batches
    applied = 0
    failed = 0

    def process_batch(batch):
        results = call_openai_batch(batch)
        if not results:
            return 0, len(batch)

        ok = 0
        bad = 0
        for k, fix in enumerate(batch):
            if k < len(results) and results[k]:
                new_think = results[k].strip()
                # Validate: no Chinese, not empty, reasonable length
                if new_think and not CHINESE_PAT.search(new_think) and len(new_think) > 10:
                    i, j = fix["entry_idx"], fix["msg_idx"]
                    old = entries[i]["messages"][j]["content"]
                    entries[i]["messages"][j]["content"] = THINK_PAT.sub(
                        f"<think>{new_think}</think>", old, count=1
                    )
                    ok += 1
                else:
                    bad += 1
            else:
                bad += 1
        return ok, bad

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_batch, b): b for b in batches}
        done_count = 0
        for future in as_completed(futures):
            ok, bad = future.result()
            applied += ok
            failed += bad
            done_count += 1
            if done_count % 20 == 0:
                print(f"  [{done_count}/{len(batches)}] applied={applied} failed={failed}")

    print(f"\nDone: {applied} thinks regenerated, {failed} failed")
    print(f"Success rate: {applied * 100 // max(applied + failed, 1)}%")

    with open(args.output, "w") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"Wrote {len(entries)} entries to {args.output}")


if __name__ == "__main__":
    main()
