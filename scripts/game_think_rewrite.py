#!/usr/bin/env python3
"""
GAME Think Rewrite — rewrite bot template thinks using GPT-5.4.

Keeps the original action (correct), only replaces the think block with
high-quality strategic reasoning from GPT-5.4.

Much cheaper than full distillation:
- Distillation: play entire game (~10-30 API calls per game)
- Think rewrite: 1 API call per batch of 10-15 thinks

Usage:
    # Test: rewrite 20 thinks for othello, analyze quality
    python3 scripts/game_think_rewrite.py --game othello --test 20

    # Rewrite all template thinks for a game
    python3 scripts/game_think_rewrite.py --game othello --all

    # Rewrite for multiple games
    python3 scripts/game_think_rewrite.py --game othello,clobber,gin_rummy --all

    # Quality analysis of rewritten data
    python3 scripts/game_think_rewrite.py --game othello --analyze

    # Dry run: show what would be rewritten
    python3 scripts/game_think_rewrite.py --game othello --dry-run
"""

import argparse
import json
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_DIR, ".pylibs"))

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_DIR, ".env"), override=True)

import httpx

CANONICAL = os.path.join(PROJECT_DIR, "data", "canonical", "game.jsonl")
OUTPUT_DIR = os.path.join(PROJECT_DIR, "data")

CHINESE_PAT = re.compile(r'[\u4e00-\u9fff]')
THINK_PAT = re.compile(r'<think>(.*?)</think>', re.DOTALL)

API_KEY = os.environ.get("OPENAI_API_KEY", "")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "")
MODEL = "gpt-5.4"

# Game-specific context for better think generation
GAME_CONTEXT = {
    "othello": {
        "rules": "8x8 board, place pieces to flip opponent's. Corners unflippable (best), edges stable, center flexible.",
        "strategy": "Corner control, edge stability, minimize opponent mobility, avoid giving corners. Endgame: maximize disc count.",
        "think_cues": ["board control", "corner threat", "mobility", "stable discs", "opponent options", "flip count", "edge play", "tempo"],
    },
    "clobber": {
        "rules": "Rectangular grid, capture by moving onto adjacent opponent piece. Last to move wins.",
        "strategy": "Maximize own mobility, restrict opponent captures. Lookahead for positional advantage.",
        "think_cues": ["mobility", "opponent captures", "isolated pieces", "board section", "endgame", "tempo", "adjacent threats"],
    },
    "gin_rummy": {
        "rules": "Form melds (runs/sets of 3+), minimize deadwood. Draw from stock or discard pile, knock when deadwood ≤10.",
        "strategy": "Keep meld-forming cards, discard high deadwood, draw from stock when discard unhelpful, knock early with low deadwood.",
        "think_cues": ["deadwood count", "meld potential", "run", "set", "opponent discards", "knock threshold", "draw decision"],
    },
    "hex": {
        "rules": "Connect your two edges across the board by placing stones. First to connect wins.",
        "strategy": "Control center, build bridge patterns (2-step connections), block opponent's shortest path, extend chains.",
        "think_cues": ["connection", "bridge", "chain extension", "blocking", "center control", "edge proximity", "path analysis"],
    },
    "goofspiel": {
        "rules": "Bid cards for prizes. Highest bid wins the prize. Strategy is resource allocation.",
        "strategy": "Bid proportionally to prize value, save high cards for high prizes, track opponent's remaining cards.",
        "think_cues": ["prize value", "remaining cards", "opponent range", "resource allocation", "point lead", "endgame math"],
    },
}

BATCH_SIZE = 10  # thinks per API call


def load_canonical():
    entries = []
    with open(CANONICAL) as f:
        for line in f:
            entries.append(json.loads(line))
    return entries


def find_rewritable_thinks(entries, game, max_count=0):
    """Find thinks that need rewriting (template/repetitive)."""
    # First pass: count think frequencies
    think_freq = Counter()
    for e in entries:
        if e.get("game") != game:
            continue
        for m in e["messages"]:
            if m["role"] != "assistant":
                continue
            match = THINK_PAT.search(m["content"])
            if not match:
                continue
            norm = re.sub(r'\d+', 'N', match.group(1).strip())
            think_freq[norm] += 1

    # Second pass: collect thinks to rewrite (frequency > 5 = template)
    targets = []
    for i, e in enumerate(entries):
        if e.get("game") != game:
            continue
        for j, m in enumerate(e["messages"]):
            if m["role"] != "assistant":
                continue
            match = THINK_PAT.search(m["content"])
            if not match:
                continue
            think = match.group(1).strip()
            norm = re.sub(r'\d+', 'N', think)
            action = THINK_PAT.sub("", m["content"]).strip()

            # Skip already diverse thinks (frequency ≤ 5)
            if think_freq[norm] <= 5:
                continue

            # Get game state from preceding user message
            context = ""
            if j > 0 and e["messages"][j - 1]["role"] == "user":
                context = e["messages"][j - 1]["content"][:400]

            targets.append({
                "entry_idx": i,
                "msg_idx": j,
                "think": think,
                "action": action,
                "context": context,
                "norm": norm,
                "freq": think_freq[norm],
            })

            if max_count and len(targets) >= max_count:
                return targets, think_freq

    return targets, think_freq


def rewrite_batch(batch, game):
    """Rewrite a batch of thinks using GPT-5.4."""
    gc = GAME_CONTEXT.get(game, {"rules": f"Playing {game}", "strategy": "Win the game", "think_cues": ["strategy"]})

    items = []
    for k, t in enumerate(batch):
        ctx = t["context"][:200] if t["context"] else "N/A"
        items.append(f'{k}. Action={t["action"]}, GameState="{ctx}", OldThink="{t["think"][:100]}"')

    cues = ", ".join(gc["think_cues"])

    prompt = f"""You are rewriting strategic reasoning for a {game} AI training dataset.

Game rules: {gc["rules"]}
Key strategy: {gc["strategy"]}

For each item below, generate NEW strategic reasoning (1-3 sentences) explaining WHY the action is good.

Requirements:
- Reference the specific game state (board position, cards, dice, etc.)
- Use varied vocabulary: {cues}
- Each reasoning must be UNIQUE — no two should share the same structure
- Do NOT mention the action number/ID
- Do NOT include <think> tags
- Be specific to THIS game state, not generic

Items:
{chr(10).join(items)}

Respond as a JSON array of {len(batch)} strings. Output ONLY the JSON array."""

    try:
        resp = httpx.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"model": MODEL, "max_tokens": 3000, "temperature": 0.9, "messages": [{"role": "user", "content": prompt}]},
            timeout=None,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        return parse_json_array(text)
    except Exception as e:
        print(f"  API error: {e}")
        return None


def parse_json_array(text):
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


def run_rewrite(entries, targets, game, workers=5):
    """Execute the rewrite on targets."""
    # Create batches
    batches = []
    for i in range(0, len(targets), BATCH_SIZE):
        batches.append(targets[i:i + BATCH_SIZE])

    print(f"\nRewriting {len(targets)} thinks in {len(batches)} API calls...")

    applied = 0
    failed = 0

    def process_batch(batch):
        results = rewrite_batch(batch, game)
        if not results:
            return 0, len(batch)
        ok, bad = 0, 0
        for k, t in enumerate(batch):
            if k < len(results) and results[k] and len(results[k].strip()) > 15:
                new_think = results[k].strip()
                if not CHINESE_PAT.search(new_think):
                    i, j = t["entry_idx"], t["msg_idx"]
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

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_batch, b): idx for idx, b in enumerate(batches)}
        done_count = 0
        for future in as_completed(futures):
            ok, bad = future.result()
            applied += ok
            failed += bad
            done_count += 1
            if done_count % 10 == 0 or done_count == len(batches):
                print(f"  [{done_count}/{len(batches)}] applied={applied} failed={failed}")

    print(f"\nRewrite complete: {applied} applied, {failed} failed")
    return entries, applied


def analyze_quality(entries, game, label=""):
    """Analyze think quality for a game."""
    ents = [e for e in entries if e.get("game") == game]
    if not ents:
        print(f"No entries for {game}")
        return

    thinks = []
    unique = set()
    lens = []

    for e in ents:
        for m in e["messages"]:
            if m["role"] != "assistant":
                continue
            match = THINK_PAT.search(m["content"])
            if not match:
                continue
            t = match.group(1).strip()
            thinks.append(t)
            unique.add(t[:80])
            lens.append(len(t))

    diversity = len(unique) * 100 // max(len(thinks), 1)
    avg_len = sum(lens) // max(len(lens), 1)

    print(f"\n{'='*50}")
    print(f"{game} Think Quality {label}")
    print(f"{'='*50}")
    print(f"  Entries: {len(ents)}")
    print(f"  Total thinks: {len(thinks)}")
    print(f"  Unique thinks (80ch): {len(unique)}")
    print(f"  Diversity: {diversity}%")
    print(f"  Avg think length: {avg_len} chars")

    # Show 5 random samples
    if thinks:
        print(f"\n  Sample thinks:")
        samples = random.sample(thinks, min(5, len(thinks)))
        for i, t in enumerate(samples):
            print(f"    [{i+1}] \"{t[:150]}\"")


def main():
    parser = argparse.ArgumentParser(description="GAME Think Rewrite")
    parser.add_argument("--game", required=True, help="Game name(s), comma-separated")
    parser.add_argument("--test", type=int, default=0, help="Test mode: rewrite N thinks, analyze quality")
    parser.add_argument("--all", action="store_true", help="Rewrite all template thinks")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be rewritten")
    parser.add_argument("--analyze", action="store_true", help="Analyze current think quality")
    parser.add_argument("--workers", type=int, default=5, help="API workers")
    parser.add_argument("--input", default=None, help="Input file (default: canonical)")
    parser.add_argument("--output", default=None, help="Output file")
    args = parser.parse_args()

    games = [g.strip() for g in args.game.split(",")]

    if args.input:
        entries = []
        with open(args.input) as f:
            for line in f:
                entries.append(json.loads(line))
    else:
        entries = load_canonical()
    print(f"Loaded {len(entries)} canonical entries")

    for game in games:
        print(f"\n{'#'*60}")
        print(f"# {game}")
        print(f"{'#'*60}")

        if args.analyze:
            analyze_quality(entries, game, "(current)")
            continue

        max_count = args.test if args.test > 0 else 0
        targets, think_freq = find_rewritable_thinks(entries, game, max_count)

        print(f"\nTemplate thinks (freq>5): {len(targets)}")
        print(f"Unique templates: {sum(1 for f in think_freq.values() if f > 5)}")
        print(f"Top 5 templates:")
        for norm, count in think_freq.most_common(5):
            print(f"  [{count}x] {norm[:80]}")

        if args.dry_run:
            print(f"\n[DRY RUN] Would rewrite {len(targets)} thinks")
            continue

        if not targets:
            print("Nothing to rewrite.")
            continue

        # Before quality
        analyze_quality(entries, game, "(BEFORE)")

        # Rewrite
        entries, applied = run_rewrite(entries, targets, game, workers=args.workers)

        # After quality
        analyze_quality(entries, game, "(AFTER)")

    if args.analyze or args.dry_run:
        return

    # Write output
    output = args.output or os.path.join(OUTPUT_DIR, f"game_think_rewritten.jsonl")
    with open(output, "w") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(entries)} entries to {output}")

    if args.test:
        print(f"\n{'='*60}")
        print(f"TEST COMPLETE — review output quality before running --all")
        print(f"If quality is good: python3 scripts/game_think_rewrite.py --game {','.join(games)} --all")
        print(f"Then: cp {output} {CANONICAL}")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
