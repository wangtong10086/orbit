#!/usr/bin/env python3
"""
Comprehensive GAME think block fixer using GPT-5.4.

Fixes:
1. Chinese think blocks → regenerate English strategic reasoning
2. Repetitive think blocks → generate diverse variants per template
3. Empty dice bug in liars_dice → parse real dice from game state

Strategy for efficiency:
- Repetitive: identify unique normalized templates, generate 30 variants each, randomly assign
- Chinese: batch 15 thinks per API call, regenerate from game context
- Total API calls: ~750 (vs 63000+ if done individually)

Usage:
    python3 scripts/game_think_fix.py --dry-run        # Count issues, no changes
    python3 scripts/game_think_fix.py --fix-repetitive  # Fix repetitive only
    python3 scripts/game_think_fix.py --fix-chinese     # Fix Chinese only
    python3 scripts/game_think_fix.py --all             # Fix everything
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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".pylibs"))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"), override=True)

import httpx

CANONICAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "canonical", "game.jsonl")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

CHINESE_PAT = re.compile(r'[\u4e00-\u9fff]')
THINK_PAT = re.compile(r'<think>(.*?)</think>', re.DOTALL)

API_KEY = os.environ.get("OPENAI_API_KEY", "")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "")
MODEL = "gpt-5.4"

# Threshold: normalized think appearing more than this many times is "repetitive"
REPETITIVE_THRESHOLD = 20
# How many diverse variants to generate per template
VARIANTS_PER_TEMPLATE = 30

# Game-specific strategy knowledge for better regeneration
GAME_STRATEGY_CONTEXT = {
    "goofspiel": "Goofspiel is a bidding game. Players simultaneously bid cards (0-12) for prize cards. "
                 "Strategy: bid proportionally to prize value, save high cards for high prizes, bluff occasionally.",
    "leduc_poker": "Leduc Poker has 3 cards (J,Q,K), 2 rounds. Actions: fold(0), call(1), raise(2). "
                   "Strategy: raise with K, call with Q, fold/call with J. Pairs (matching public card) are very strong.",
    "liars_dice": "Liar's Dice: players secretly roll dice, make escalating claims about total dice showing a face. "
                  "Action 60 = call Liar. Strategy: count own dice, estimate probabilities, call liar when claim seems unlikely.",
    "othello": "Othello/Reversi: place pieces to flip opponent's. Strategy: corners are best (unflippable), "
               "edges are stable, minimize opponent mobility, avoid giving corners to opponent.",
    "hex": "Hex: connect your edges across the board. Strategy: control center, build bridge patterns "
           "(two-step connections), block opponent's shortest path, extend chains toward target edges.",
    "clobber": "Clobber: capture by moving onto adjacent opponent pieces. Strategy: maximize own mobility, "
               "minimize opponent's capture options, use lookahead to find positionally strong captures.",
    "gin_rummy": "Gin Rummy: form melds (runs/sets of 3+), minimize deadwood. Strategy: keep meld-forming cards, "
                 "discard high deadwood, draw from stock when discard pile doesn't help, knock when deadwood is low.",
}


def load_entries():
    entries = []
    with open(CANONICAL) as f:
        for line in f:
            entries.append(json.loads(line))
    return entries


def normalize_think(think_text):
    """Normalize think text by replacing numbers with N."""
    return re.sub(r'\d+', 'N', think_text)


def call_gpt54(prompt, max_tokens=2000, temperature=0.9):
    """Call GPT-5.4 API."""
    try:
        resp = httpx.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=90.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
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


# ============================================================
# Phase 1: Fix repetitive thinks
# ============================================================

def find_repetitive_templates(entries):
    """Find normalized think templates appearing > REPETITIVE_THRESHOLD times."""
    game_templates = defaultdict(Counter)
    game_examples = defaultdict(dict)  # game -> {normalized: original_example}

    for e in entries:
        game = e.get("game", "unknown")
        for m in e["messages"]:
            if m["role"] != "assistant":
                continue
            match = THINK_PAT.search(m["content"])
            if not match:
                continue
            think = match.group(1).strip()
            if CHINESE_PAT.search(think):
                continue  # Skip Chinese, handled separately
            norm = normalize_think(think)
            game_templates[game][norm] += 1
            if norm not in game_examples[game]:
                game_examples[game][norm] = think

    result = {}
    for game in game_templates:
        for norm, count in game_templates[game].items():
            if count > REPETITIVE_THRESHOLD:
                key = (game, norm)
                result[key] = {
                    "game": game,
                    "normalized": norm,
                    "example": game_examples[game][norm],
                    "count": count,
                }
    return result


def generate_variants_for_template(game, template_example, n_variants=VARIANTS_PER_TEMPLATE):
    """Generate diverse think variants for a repetitive template."""
    context = GAME_STRATEGY_CONTEXT.get(game, "")

    prompt = f"""You are generating diverse strategic reasoning for a {game} AI training dataset.

Game info: {context}

The current reasoning is too repetitive. Here's the template being overused:
"{template_example}"

Generate {n_variants} diverse alternative strategic reasoning phrases for similar game situations.
Each should:
- Be 1-2 sentences, concise
- Explain a specific strategic insight for {game}
- Use varied vocabulary and sentence structures
- Reference specific game concepts (positions, probabilities, piece values, etc.)
- Sound like natural internal reasoning, not a textbook

Output as a JSON array of {n_variants} strings. Example: ["reasoning 1", "reasoning 2", ...]
Output ONLY the JSON array, nothing else."""

    text = call_gpt54(prompt, max_tokens=3000, temperature=0.95)
    if not text:
        return None
    variants = parse_json_array(text)
    if variants and len(variants) >= n_variants // 2:
        # Filter out any that still have Chinese or are too short
        variants = [v.strip() for v in variants if v and len(v.strip()) > 10 and not CHINESE_PAT.search(v)]
        return variants
    return None


def fix_repetitive(entries, workers=5):
    """Fix repetitive think blocks by generating diverse variants."""
    templates = find_repetitive_templates(entries)
    if not templates:
        print("No repetitive templates found.")
        return entries

    print(f"\nFound {len(templates)} repetitive templates to diversify:")
    for key, info in sorted(templates.items(), key=lambda x: -x[1]["count"]):
        print(f"  {info['game']}: {info['count']}x — {info['normalized'][:70]}")

    # Generate variants for each template
    print(f"\nGenerating {VARIANTS_PER_TEMPLATE} variants per template...")
    template_variants = {}

    def gen_one(key, info):
        variants = generate_variants_for_template(info["game"], info["example"])
        return key, variants

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(gen_one, k, v): k for k, v in templates.items()}
        done = 0
        for future in as_completed(futures):
            key, variants = future.result()
            done += 1
            if variants:
                template_variants[key] = variants
                print(f"  [{done}/{len(templates)}] {key[0]}: {len(variants)} variants generated")
            else:
                print(f"  [{done}/{len(templates)}] {key[0]}: FAILED")

    print(f"\nVariants generated for {len(template_variants)}/{len(templates)} templates")

    # Apply variants: replace repetitive thinks with random variant
    random.seed(42)
    replaced = 0
    for e in entries:
        game = e.get("game", "unknown")
        for m in e["messages"]:
            if m["role"] != "assistant":
                continue
            match = THINK_PAT.search(m["content"])
            if not match:
                continue
            think = match.group(1).strip()
            if CHINESE_PAT.search(think):
                continue
            norm = normalize_think(think)
            key = (game, norm)
            if key in template_variants:
                new_think = random.choice(template_variants[key])
                m["content"] = THINK_PAT.sub(f"<think>{new_think}</think>", m["content"], count=1)
                replaced += 1

    print(f"Replaced {replaced} repetitive think blocks")
    return entries


# ============================================================
# Phase 2: Fix Chinese thinks
# ============================================================

def find_chinese_thinks(entries):
    """Find all Chinese think blocks with their locations."""
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
            if not CHINESE_PAT.search(think):
                continue
            action = THINK_PAT.sub("", m["content"]).strip()
            # Get game context from preceding user message
            context = ""
            if j > 0 and e["messages"][j - 1]["role"] == "user":
                context = e["messages"][j - 1]["content"][:300]
            fixes.append({
                "entry_idx": i,
                "msg_idx": j,
                "game": game,
                "think": think,
                "action": action,
                "context": context,
            })
    return fixes


def translate_batch(batch, batch_idx, total_batches):
    """Translate/regenerate a batch of Chinese thinks."""
    game = batch[0]["game"]
    game_context = GAME_STRATEGY_CONTEXT.get(game, "")

    items = []
    for k, fix in enumerate(batch):
        ctx = fix["context"][:100] if fix["context"] else "N/A"
        items.append(f'{k}. Action={fix["action"]}, Chinese="{fix["think"][:120]}", GameState="{ctx}"')

    prompt = f"""You are regenerating strategic reasoning for a {game} AI training dataset.
The original reasoning was in Chinese and needs to be replaced with natural English.

Game info: {game_context}

For each item below, generate concise English strategic reasoning (1-2 sentences) that:
- Explains WHY the chosen action is strategically good in this game state
- Uses {game}-specific terminology and concepts
- Is diverse (vary your phrasing across items)
- Does NOT mention the action ID number
- Does NOT include <think> tags

Items:
{chr(10).join(items)}

Respond as a JSON array of {len(batch)} strings, one per item, in order.
Output ONLY the JSON array."""

    text = call_gpt54(prompt, max_tokens=2000, temperature=0.8)
    if not text:
        return None
    results = parse_json_array(text)
    if results and len(results) == len(batch):
        return results
    if results and len(results) >= len(batch) * 0.8:
        # Pad with None for missing
        while len(results) < len(batch):
            results.append(None)
        return results
    return None


def fix_chinese(entries, workers=5, batch_size=15):
    """Fix Chinese think blocks by regenerating English versions via GPT-5.4."""
    fixes = find_chinese_thinks(entries)
    if not fixes:
        print("No Chinese thinks found.")
        return entries

    print(f"\nFound {len(fixes)} Chinese think blocks to fix")

    # Group by game for better batching
    by_game = defaultdict(list)
    for fix in fixes:
        by_game[fix["game"]].append(fix)

    for game, game_fixes in by_game.items():
        print(f"  {game}: {len(game_fixes)} thinks")

    # Create batches
    batches = []
    for game, game_fixes in by_game.items():
        for i in range(0, len(game_fixes), batch_size):
            batches.append(game_fixes[i:i + batch_size])

    print(f"\nAPI calls needed: {len(batches)} (batch_size={batch_size})")

    # Process batches
    applied = 0
    failed = 0

    def process_batch(batch, idx):
        results = translate_batch(batch, idx, len(batches))
        if not results:
            return 0, len(batch)
        ok, bad = 0, 0
        for k, fix in enumerate(batch):
            if k < len(results) and results[k] and len(results[k].strip()) > 10:
                new_think = results[k].strip()
                if not CHINESE_PAT.search(new_think):
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

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_batch, b, idx): idx for idx, b in enumerate(batches)}
        done_count = 0
        for future in as_completed(futures):
            ok, bad = future.result()
            applied += ok
            failed += bad
            done_count += 1
            if done_count % 20 == 0 or done_count == len(batches):
                print(f"  [{done_count}/{len(batches)}] applied={applied} failed={failed}")

    print(f"\nChinese fix complete: {applied} translated, {failed} failed")
    return entries


# ============================================================
# Phase 3: Fix liars_dice empty dice bug
# ============================================================

def fix_empty_dice(entries):
    """Fix liars_dice entries that still show 'My dice []' in thinks."""
    fixed = 0
    for e in entries:
        if e.get("game") != "liars_dice":
            continue
        # Find player's dice from user messages
        player_dice = None
        for m in e["messages"]:
            if m["role"] == "user":
                # Look for dice info in game state
                dice_match = re.search(r'Your dice:?\s*\[([^\]]+)\]', m["content"])
                if not dice_match:
                    dice_match = re.search(r'you rolled:?\s*\[([^\]]+)\]', m["content"], re.IGNORECASE)
                if dice_match:
                    player_dice = dice_match.group(1)

        if not player_dice:
            continue

        # Fix think blocks with empty dice
        for m in e["messages"]:
            if m["role"] != "assistant":
                continue
            if "dice []" in m["content"] or "My dice []" in m["content"]:
                m["content"] = m["content"].replace("dice []", f"dice [{player_dice}]")
                m["content"] = m["content"].replace("My dice []", f"My dice [{player_dice}]")
                fixed += 1

    print(f"Fixed {fixed} empty dice references in liars_dice")
    return entries


# ============================================================
# Audit
# ============================================================

def audit(entries):
    """Quick audit of think block quality."""
    print("=" * 60)
    print("GAME Data Quality Audit")
    print("=" * 60)

    for game in ["goofspiel", "liars_dice", "leduc_poker", "gin_rummy", "othello", "hex", "clobber"]:
        ents = [e for e in entries if e.get("game") == game]
        if not ents:
            continue

        total_thinks = 0
        cn_thinks = 0
        unique_thinks = set()

        for e in ents:
            for m in e["messages"]:
                if m["role"] != "assistant":
                    continue
                match = THINK_PAT.search(m["content"])
                if not match:
                    continue
                think = match.group(1).strip()
                total_thinks += 1
                if CHINESE_PAT.search(think):
                    cn_thinks += 1
                unique_thinks.add(think[:80])

        diversity = len(unique_thinks) / max(total_thinks, 1) * 100
        print(f"  {game}: {len(ents)} entries, {total_thinks} thinks, "
              f"CN={cn_thinks}, diversity={diversity:.1f}% ({len(unique_thinks)} unique)")

    print()


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Comprehensive GAME think fixer")
    parser.add_argument("--dry-run", action="store_true", help="Audit only, no changes")
    parser.add_argument("--fix-repetitive", action="store_true", help="Fix repetitive thinks")
    parser.add_argument("--fix-chinese", action="store_true", help="Fix Chinese thinks")
    parser.add_argument("--fix-dice", action="store_true", help="Fix empty dice bug")
    parser.add_argument("--all", action="store_true", help="Fix everything")
    parser.add_argument("--workers", type=int, default=5, help="API worker threads")
    parser.add_argument("--batch-size", type=int, default=15, help="Thinks per API batch")
    parser.add_argument("--output", default=None, help="Output file (default: data/game_fixed.jsonl)")
    args = parser.parse_args()

    if args.all:
        args.fix_repetitive = True
        args.fix_chinese = True
        args.fix_dice = True

    entries = load_entries()
    print(f"Loaded {len(entries)} entries from canonical\n")

    print("--- BEFORE ---")
    audit(entries)

    if args.dry_run or not any([args.fix_repetitive, args.fix_chinese, args.fix_dice]):
        print("Dry run complete. Use --all to fix everything.")
        return

    # Order matters: fix repetitive first (so Chinese entries aren't touched),
    # then Chinese, then dice
    if args.fix_repetitive:
        print("\n" + "=" * 60)
        print("PHASE 1: Fixing repetitive thinks")
        print("=" * 60)
        entries = fix_repetitive(entries, workers=args.workers)

    if args.fix_chinese:
        print("\n" + "=" * 60)
        print("PHASE 2: Fixing Chinese thinks")
        print("=" * 60)
        entries = fix_chinese(entries, workers=args.workers, batch_size=args.batch_size)

    if args.fix_dice:
        print("\n" + "=" * 60)
        print("PHASE 3: Fixing empty dice bug")
        print("=" * 60)
        entries = fix_empty_dice(entries)

    print("\n--- AFTER ---")
    audit(entries)

    # Write output
    output = args.output or os.path.join(OUTPUT_DIR, "game_fixed.jsonl")
    with open(output, "w") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(entries)} entries to {output}")
    print("Review the output, then replace canonical with:")
    print(f"  cp {output} {CANONICAL}")


if __name__ == "__main__":
    main()
