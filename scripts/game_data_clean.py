#!/usr/bin/env python3
"""
GAME canonical data cleaner and think-block regenerator.

Tasks:
1. Replace Chinese think blocks with English using Claude API
2. Improve low-diversity think blocks (gin_rummy templates)
3. Remove entries without think blocks
4. Downsample SFT-unlearnable games
5. Validate format compliance

Usage:
    python3 scripts/game_data_clean.py --audit          # Dry run, show issues
    python3 scripts/game_data_clean.py --clean           # Clean + write output
    python3 scripts/game_data_clean.py --regen-thinks    # Regenerate thinks via Claude API
"""

import argparse
import json
import os
import re
import sys
import time
import random
from collections import Counter, defaultdict
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"), override=True)

CANONICAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "canonical", "game.jsonl")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

CHINESE_PAT = re.compile(r'[\u4e00-\u9fff]')
THINK_PAT = re.compile(r'<think>(.*?)</think>', re.DOTALL)

# SFT-unlearnable games — keep only a small sample
UNLEARNABLE_GAMES = {"liars_dice", "othello", "hex", "clobber"}
UNLEARNABLE_MAX = 50  # per game

# Known low-quality templates to flag
LOW_QUALITY_TEMPLATES = {
    "Organize hand, keep cards that form melds, discard highest deadwood.",
    "My dice [], face 1 appears 0 times. Conservative bid, avoid overbidding.",
    "Only one legal action available.",
}


def load_canonical():
    entries = []
    with open(CANONICAL) as f:
        for line in f:
            entries.append(json.loads(line))
    return entries


def audit(entries):
    """Full quality audit of canonical GAME data."""
    stats = defaultdict(lambda: defaultdict(int))
    issues = []

    for i, e in enumerate(entries):
        game = e.get("game", "unknown")
        source = e.get("source", "unknown")
        stats[game]["total"] += 1
        stats[game][f"src_{source}"] += 1

        asst_msgs = [m for m in e["messages"] if m["role"] == "assistant"]
        has_any_think = False
        has_chinese = False
        has_template = False
        has_no_think_msg = False

        for m in asst_msgs:
            content = m["content"]
            think_match = THINK_PAT.search(content)

            if think_match:
                has_any_think = True
                think_text = think_match.group(1).strip()
                if CHINESE_PAT.search(think_text):
                    has_chinese = True
                if think_text in LOW_QUALITY_TEMPLATES:
                    has_template = True
            else:
                has_no_think_msg = True

            # Validate action format
            after_think = THINK_PAT.sub("", content).strip()
            if not re.match(r"^\d+$", after_think):
                stats[game]["invalid_action"] += 1

        if has_chinese:
            stats[game]["chinese_think"] += 1
        if has_template:
            stats[game]["template_think"] += 1
        if not has_any_think:
            stats[game]["no_think"] += 1
        if has_no_think_msg and has_any_think:
            stats[game]["partial_think"] += 1

    print("=" * 70)
    print("GAME Canonical Data Audit")
    print("=" * 70)
    total = sum(stats[g]["total"] for g in stats)
    print(f"Total entries: {total}\n")

    for game in sorted(stats.keys()):
        s = stats[game]
        print(f"  {game}: {s['total']} entries")
        for k, v in sorted(s.items()):
            if k != "total" and v > 0:
                print(f"    {k}: {v}")
        print()

    # Summary
    chinese_total = sum(stats[g].get("chinese_think", 0) for g in stats)
    no_think_total = sum(stats[g].get("no_think", 0) for g in stats)
    template_total = sum(stats[g].get("template_think", 0) for g in stats)
    unlearnable_total = sum(stats[g]["total"] for g in UNLEARNABLE_GAMES if g in stats)

    print("ISSUES SUMMARY:")
    print(f"  Chinese think blocks: {chinese_total}")
    print(f"  Entries without any think: {no_think_total}")
    print(f"  Template/low-quality thinks: {template_total}")
    print(f"  SFT-unlearnable game entries: {unlearnable_total}")
    print(f"  Target unlearnable entries: {UNLEARNABLE_MAX * len(UNLEARNABLE_GAMES)}")

    return stats


def clean(entries):
    """
    Clean canonical data:
    1. Remove entries with no think blocks at all
    2. Downsample unlearnable games
    3. Flag Chinese think entries for API regeneration
    """
    cleaned = []
    removed = defaultdict(int)
    unlearnable_counts = defaultdict(int)

    # Shuffle unlearnable games to get diverse sample
    random.seed(42)
    shuffled = list(entries)
    random.shuffle(shuffled)

    for e in shuffled:
        game = e.get("game", "unknown")
        asst_msgs = [m for m in e["messages"] if m["role"] == "assistant"]
        has_any_think = any("<think>" in m["content"] for m in asst_msgs)

        # Rule 1: Remove entries without any think blocks
        if not has_any_think:
            removed[f"{game}_no_think"] += 1
            continue

        # Rule 2: Downsample SFT-unlearnable games
        if game in UNLEARNABLE_GAMES:
            if unlearnable_counts[game] >= UNLEARNABLE_MAX:
                removed[f"{game}_unlearnable_downsample"] += 1
                continue
            unlearnable_counts[game] += 1

        cleaned.append(e)

    # Sort back by game for consistency
    cleaned.sort(key=lambda e: (e.get("game", ""), e.get("task_id", 0)))

    print(f"\nCleaning results:")
    print(f"  Input: {len(entries)}")
    print(f"  Output: {len(cleaned)}")
    print(f"  Removed: {sum(removed.values())}")
    for k, v in sorted(removed.items()):
        print(f"    {k}: {v}")

    return cleaned


def translate_think_claude(think_text, game, action_id, api_key, base_url):
    """Translate Chinese think block to strategic English using Claude API."""
    import httpx

    prompt = f"""You are translating game strategy reasoning from Chinese to English for a {game} game AI training dataset.

The original Chinese reasoning:
{think_text}

The action chosen was: {action_id}

Translate this into natural English strategic reasoning. Requirements:
- Keep it concise (1-3 sentences)
- Focus on the game strategy (why this action is good)
- Use game-specific terminology
- Do NOT include the action ID in the reasoning
- Do NOT wrap in <think> tags

Output ONLY the English reasoning text, nothing else."""

    resp = httpx.post(
        f"{base_url}/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 150,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["content"][0]["text"].strip()


def diversify_think_claude(game, action_id, game_state_summary, api_key, base_url):
    """Generate diverse strategic reasoning for a game action using Claude API."""
    import httpx

    prompt = f"""Generate strategic reasoning for a {game} AI player who chose action {action_id}.

Game context: {game_state_summary}

Requirements:
- 1-3 sentences of natural strategic reasoning
- Explain WHY this action is good strategy
- Use specific {game} terminology and concepts
- Be diverse — don't use template phrases
- Do NOT include the action ID
- Do NOT wrap in <think> tags

Output ONLY the reasoning text."""

    resp = httpx.post(
        f"{base_url}/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 150,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["content"][0]["text"].strip()


def regen_thinks(entries, max_regen=500, workers=5):
    """Regenerate Chinese and template think blocks using Claude API."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")

    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        return entries

    to_fix = []
    for i, e in enumerate(entries):
        game = e.get("game", "unknown")
        for j, m in enumerate(e["messages"]):
            if m["role"] != "assistant":
                continue
            think_match = THINK_PAT.search(m["content"])
            if not think_match:
                continue
            think_text = think_match.group(1).strip()
            action = THINK_PAT.sub("", m["content"]).strip()

            needs_fix = False
            reason = ""
            if CHINESE_PAT.search(think_text):
                needs_fix = True
                reason = "chinese"
            elif think_text in LOW_QUALITY_TEMPLATES:
                needs_fix = True
                reason = "template"

            if needs_fix and len(to_fix) < max_regen:
                # Get game context from preceding user message
                context = ""
                if j > 0 and e["messages"][j - 1]["role"] == "user":
                    context = e["messages"][j - 1]["content"][:300]
                to_fix.append({
                    "entry_idx": i,
                    "msg_idx": j,
                    "game": game,
                    "think_text": think_text,
                    "action": action,
                    "context": context,
                    "reason": reason,
                })

    print(f"Think blocks to regenerate: {len(to_fix)}")
    if not to_fix:
        return entries

    # Process with ThreadPoolExecutor
    success = 0
    failed = 0

    def process_one(fix):
        try:
            if fix["reason"] == "chinese":
                new_think = translate_think_claude(
                    fix["think_text"], fix["game"], fix["action"],
                    api_key, base_url
                )
            else:
                new_think = diversify_think_claude(
                    fix["game"], fix["action"], fix["context"],
                    api_key, base_url
                )
            return fix, new_think
        except Exception as e:
            return fix, None

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_one, fix): fix for fix in to_fix}
        for future in as_completed(futures):
            fix, new_think = future.result()
            if new_think:
                i, j = fix["entry_idx"], fix["msg_idx"]
                old_content = entries[i]["messages"][j]["content"]
                # Replace think block content
                new_content = THINK_PAT.sub(
                    f"<think>{new_think}</think>",
                    old_content,
                    count=1,
                )
                entries[i]["messages"][j]["content"] = new_content
                success += 1
            else:
                failed += 1

            if (success + failed) % 50 == 0:
                print(f"  Progress: {success} success, {failed} failed / {len(to_fix)} total")

    print(f"\nRegeneration complete: {success} success, {failed} failed")
    return entries


def add_thinks_to_bare_messages(entries):
    """Add think blocks to assistant messages that only have an action ID.

    For messages that are just a bare integer (no think block), wrap them with
    a minimal strategic think based on the game context.
    """
    game_think_templates = {
        "goofspiel": [
            "Considering the prize value and my remaining cards, this bid balances risk and reward.",
            "Allocating resources proportionally to the prize card value.",
            "Saving stronger cards for higher-value prizes later in the game.",
        ],
        "leduc_poker": [
            "Evaluating hand strength relative to the community card and pot odds.",
            "Position and card strength guide this decision.",
            "Balancing aggression with information available about opponent's range.",
        ],
        "gin_rummy": [
            "Focusing on reducing deadwood while building toward melds.",
            "This card choice improves meld potential and lowers deadwood count.",
            "Prioritizing cards that contribute to runs or sets in my hand.",
        ],
        "liars_dice": [
            "Assessing probability based on my dice and opponent's likely holdings.",
            "Using Bayesian reasoning about total dice distribution.",
            "Weighing the risk of overbidding against calling Liar.",
        ],
        "othello": [
            "Targeting stable positions to build long-term board control.",
            "Minimizing opponent mobility while securing strategic squares.",
            "Board position and flip potential drive this move selection.",
        ],
        "hex": [
            "Building connections toward my target edges while blocking opponent paths.",
            "Center control and bridge patterns strengthen my position.",
            "Maintaining connectivity while denying opponent's shortest path.",
        ],
        "clobber": [
            "Maximizing my capture options while restricting opponent mobility.",
            "This capture creates the strongest positional advantage.",
            "Balancing immediate captures with long-term board control.",
        ],
    }

    fixed = 0
    for e in entries:
        game = e.get("game", "unknown")
        templates = game_think_templates.get(game, ["Strategic reasoning guides this action."])
        for m in e["messages"]:
            if m["role"] == "assistant":
                content = m["content"].strip()
                if re.match(r"^\d+$", content):
                    think = random.choice(templates)
                    m["content"] = f"<think>{think}</think>\n{content}"
                    fixed += 1

    print(f"Added think blocks to {fixed} bare action messages")
    return entries


def write_output(entries, suffix="cleaned"):
    outpath = os.path.join(OUTPUT_DIR, f"game_{suffix}.jsonl")
    with open(outpath, "w") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"Wrote {len(entries)} entries to {outpath}")
    return outpath


def main():
    parser = argparse.ArgumentParser(description="GAME data cleaner")
    parser.add_argument("--audit", action="store_true", help="Audit only, no changes")
    parser.add_argument("--clean", action="store_true", help="Clean: remove no-think, downsample unlearnable")
    parser.add_argument("--regen-thinks", action="store_true", help="Regenerate Chinese/template thinks via Claude API")
    parser.add_argument("--add-thinks", action="store_true", help="Add think blocks to bare action messages")
    parser.add_argument("--max-regen", type=int, default=500, help="Max thinks to regenerate")
    parser.add_argument("--workers", type=int, default=5, help="API workers")
    parser.add_argument("--all", action="store_true", help="Run full pipeline: clean + add-thinks + regen-thinks")
    args = parser.parse_args()

    entries = load_canonical()
    print(f"Loaded {len(entries)} canonical entries")

    if args.audit or not any([args.clean, args.regen_thinks, args.add_thinks, args.all]):
        audit(entries)
        return

    if args.all:
        args.clean = True
        args.add_thinks = True
        args.regen_thinks = True

    if args.clean:
        entries = clean(entries)

    if args.add_thinks:
        entries = add_thinks_to_bare_messages(entries)

    if args.regen_thinks:
        entries = regen_thinks(entries, max_regen=args.max_regen, workers=args.workers)

    # Final audit
    print("\n--- Post-processing audit ---")
    audit(entries)

    # Write output
    write_output(entries, "cleaned")


if __name__ == "__main__":
    main()
