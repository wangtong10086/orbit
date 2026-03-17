#!/usr/bin/env python3
"""
GAME (OpenSpiel) high-quality data distiller

Uses local OpenSpiel engine + MCTS opponent + remote LLM API to generate training data.
Prioritizes fast games (liars_dice ~1K tok, leduc_poker ~1.3K tok, goofspiel ~7.8K tok).

Usage:
    python3 scripts/game_gen.py --seeds-per-game 50 -o data/game_gen.jsonl
    python3 scripts/game_gen.py --games liars_dice,leduc_poker --seeds-per-game 20
    python3 scripts/game_gen.py --tier 1 --seeds-per-game 30  # Tier 1 games only
"""

import asyncio
import argparse
import json
import os
import sys
import time
import random
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"), override=True)

OPENSPIEL_DIR = os.environ.get("OPENSPIEL_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "affinetes", "environments", "openspiel"))
TEMPLATES_DIR = os.environ.get("AFFINETES_TEMPLATES_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "affinetes", "affinetes", "templates"))
sys.path.insert(0, OPENSPIEL_DIR)
sys.path.insert(0, TEMPLATES_DIR)

# Game tiers by speed and quality (tokens, success rate from docs)
GAME_TIERS = {
    1: [  # Fast, high success rate
        ("liars_dice", 1100),
        ("leduc_poker", 1300),
        ("goofspiel", 7800),
        ("euchre", 5800),
        ("phantom_ttt", 1200),
        ("blackjack", 519),
    ],
    2: [  # Medium speed
        ("hex", 13900),
        ("clobber", 16900),
        ("hearts", 27500),
        ("quoridor", 38900),
    ],
    3: [  # Slower, higher token cost
        ("dots_and_boxes", 62100),
        ("checkers", 83800),
        ("othello", 105800),
        ("oware", 10000),
        ("amazons", 15000),
    ],
    4: [  # Very slow / high token cost — use sparingly
        ("go", 119100),
        ("gin_rummy", 167800),
        ("chess", 287100),
        ("backgammon", 347200),
        ("2048", 20000),
        ("solitaire", 30000),
        ("bridge", 50000),
    ],
}

# Flatten for lookup
ALL_GAMES = {}
for tier, games in GAME_TIERS.items():
    for name, avg_tokens in games:
        ALL_GAMES[name] = {"tier": tier, "avg_tokens": avg_tokens}


def parse_args():
    parser = argparse.ArgumentParser(description="GAME distillation data generation")
    parser.add_argument("-o", "--output", default="data/game_gen.jsonl", help="Output file")
    parser.add_argument("--seeds-per-game", type=int, default=20, help="Seeds per game")
    parser.add_argument("--start-seed", type=int, default=5000, help="Starting seed")
    parser.add_argument("--model", default="qwen3-max", help="LLM model")
    parser.add_argument("--base-url", default="https://dashscope-us.aliyuncs.com/compatible-mode/v1", help="API URL")
    parser.add_argument("--games", help="Comma-separated game names (e.g., liars_dice,goofspiel)")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3, 4], help="Only run specified tier")
    parser.add_argument("--max-tier", type=int, default=3, help="Max tier (default 3, skips slowest)")
    parser.add_argument("--min-score", type=float, default=0.7, help="Minimum score threshold")
    parser.add_argument("--timeout", type=int, default=600, help="Per-game timeout seconds")
    parser.add_argument("--opponent", default="mcts", choices=["mcts", "random"], help="Opponent type")
    parser.add_argument("--cot", action="store_true", help="Enable CoT annotation: batch-add <think> reasoning after games")
    return parser.parse_args()


def select_games(args) -> list[str]:
    """Select games based on CLI args."""
    if args.games:
        names = [g.strip() for g in args.games.split(",")]
        for n in names:
            if n not in ALL_GAMES:
                print(f"Warning: unknown game '{n}', skipping")
        return [n for n in names if n in ALL_GAMES]

    if args.tier:
        return [name for name, _ in GAME_TIERS[args.tier]]

    # Default: all games up to max_tier
    selected = []
    for tier in range(1, args.max_tier + 1):
        selected.extend(name for name, _ in GAME_TIERS[tier])
    return selected


def generate_task_id(game_name: str, config_id: int) -> int:
    """Generate task_id in GGGGCCCCCCCC format."""
    from game_config import AVAILABLE_GAMES
    game_idx = AVAILABLE_GAMES.index(game_name)
    return game_idx * 100_000_000 + (config_id % 100_000_000)


async def run_single_game(game_name: str, seed: int, task_id: int,
                          model: str, base_url: str, api_key: str,
                          timeout: int, opponent: str) -> dict:
    """Run a single game evaluation and return the result."""
    from env import Actor
    actor = Actor(api_key=api_key)
    try:
        result = await actor.evaluate(
            task_id=task_id,
            seed=seed,
            model=model,
            base_url=base_url,
            timeout=timeout,
            temperature=0.0,
            api_key=api_key,
            opponent=opponent,
        )
        return result
    finally:
        pass  # Actor has no shutdown method


def extract_sft_record(result: dict, game_name: str, task_id: int, seed: int) -> dict | None:
    """Extract SFT training record from game result."""
    if not result or result.get("error"):
        return None

    score = result.get("score", 0)
    conversation = result.get("extra", {}).get("conversation", [])
    if not conversation:
        return None

    # Clean messages
    clean_msgs = []
    for msg in conversation:
        content = msg.get("content", "")
        if content is None:
            content = ""
        clean_msgs.append({"role": msg["role"], "content": content})

    # Must end with assistant
    if not clean_msgs or clean_msgs[-1]["role"] != "assistant":
        return None

    # Merge consecutive same-role messages
    merged = [clean_msgs[0]]
    for m in clean_msgs[1:]:
        if m["role"] == merged[-1]["role"]:
            merged[-1]["content"] += "\n\n" + m["content"]
        else:
            merged.append(m)

    return {
        "messages": merged,
        "env": "GAME",
        "source": "distillation",
        "distill_model": None,  # filled by caller
        "score": score,
        "task_id": task_id,
        "game": game_name,
        "seed": seed,
    }


async def annotate_cot(messages: list[dict], game_name: str, model: str, base_url: str, api_key: str) -> list[dict] | None:
    """Add <think>reasoning</think> to each assistant message via LLM batch annotation."""
    import openai
    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

    annotated = []
    for i, msg in enumerate(messages):
        if msg["role"] != "assistant":
            annotated.append(msg)
            continue

        action = msg["content"].strip()
        # Build context: all messages up to this point
        context = messages[:i]
        prompt = (
            f"You are playing {game_name}. Based on the following conversation context, explain why you chose action `{action}`.\n"
            f"First analyze the current game state and available actions, then explain your reasoning.\n"
            f"Format: output <think>your analysis</think> followed by a newline and the action ID.\n"
            f"Only output <think>...</think>\\n{action}, nothing else."
        )
        context_msgs = context + [{"role": "user", "content": prompt}]

        try:
            resp = await client.chat.completions.create(
                model=model, messages=context_msgs,
                temperature=0.3, max_tokens=512,
            )
            cot_text = resp.choices[0].message.content.strip()
            # Validate: must contain <think> and the action
            if "<think>" in cot_text and action in cot_text:
                annotated.append({"role": "assistant", "content": cot_text})
            else:
                # Wrap it ourselves
                annotated.append({"role": "assistant", "content": f"<think>{cot_text}</think>\n{action}"})
        except Exception:
            return None  # Annotation failed, skip this record

    return annotated


async def main():
    args = parse_args()
    api_key = os.getenv("QWEN_API_KEY") or os.getenv("CHUTES_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        print("Error: QWEN_API_KEY not set")
        sys.exit(1)

    games = select_games(args)
    if not games:
        print("No games selected")
        sys.exit(1)

    total_tasks = len(games) * args.seeds_per_game
    print(f"GAME distillation data generation")
    print(f"  Games: {len(games)} ({', '.join(games)})")
    print(f"  Seeds/game: {args.seeds_per_game}")
    print(f"  Total tasks: {total_tasks}")
    print(f"  Model: {args.model}")
    print(f"  Opponent: {args.opponent}")
    print(f"  Output: {args.output}")
    print(f"  Min score: {args.min_score}")
    print()

    # Build task queue — randomize order for diversity
    tasks = []
    for game_name in games:
        for i in range(args.seeds_per_game):
            seed = args.start_seed + i
            config_id = random.randint(0, 99_999_999)
            task_id = generate_task_id(game_name, config_id)
            tasks.append((game_name, seed, task_id))
    random.shuffle(tasks)

    # Change to openspiel dir for imports
    original_dir = os.getcwd()
    os.chdir(OPENSPIEL_DIR)

    # Ensure output dir exists
    output_path = os.path.join(original_dir, args.output)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    success = 0
    failed = 0
    filtered = 0
    game_stats = {}  # per-game success tracking

    for idx, (game_name, seed, task_id) in enumerate(tasks):
        tier = ALL_GAMES[game_name]["tier"]
        print(f"[{idx+1}/{total_tasks}] {game_name} seed={seed} (T{tier})", end=" ", flush=True)

        try:
            result = await asyncio.wait_for(
                run_single_game(game_name, seed, task_id, args.model, args.base_url,
                                api_key, args.timeout, args.opponent),
                timeout=args.timeout + 30,
            )

            score = result.get("score", 0)
            error = result.get("error")
            conv = result.get("extra", {}).get("conversation", [])
            total_chars = sum(len(str(m.get("content", ""))) for m in conv)

            if error:
                failed += 1
                print(f"✗ error: {str(error)[:80]}")
            elif score >= args.min_score:
                record = extract_sft_record(result, game_name, task_id, seed)
                if record:
                    # CoT annotation if requested
                    if args.cot:
                        print(f"→ CoT annotating...", end=" ", flush=True)
                        cot_msgs = await annotate_cot(
                            record["messages"], game_name, args.model,
                            args.base_url, api_key)
                        if cot_msgs:
                            record["messages"] = cot_msgs
                            # Verify all assistant msgs have <think>
                            ast_count = sum(1 for m in cot_msgs if m["role"] == "assistant")
                            think_count = sum(1 for m in cot_msgs if m["role"] == "assistant" and "<think>" in m.get("content", ""))
                            print(f"✓ {think_count}/{ast_count}", end=" ", flush=True)
                        else:
                            filtered += 1
                            print(f"✗ cot_failed")
                            continue

                    record["distill_model"] = args.model
                    with open(output_path, "a") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    success += 1
                    game_stats.setdefault(game_name, {"ok": 0, "fail": 0})["ok"] += 1
                    print(f"✓ score={score:.2f} msgs={len(conv)} chars={total_chars:,}")
                else:
                    filtered += 1
                    print(f"✗ filtered (format)")
            else:
                filtered += 1
                game_stats.setdefault(game_name, {"ok": 0, "fail": 0})["fail"] += 1
                print(f"✗ low_score={score:.2f}")

        except asyncio.TimeoutError:
            failed += 1
            print("✗ timeout")
        except Exception as e:
            failed += 1
            print(f"✗ {type(e).__name__}: {str(e)[:80]}")

    os.chdir(original_dir)

    print(f"\n{'='*60}")
    print(f"Done: {success} success / {filtered} filtered / {failed} failed (total {total_tasks})")
    print(f"Success rate: {success*100//max(total_tasks,1)}%")
    if game_stats:
        print(f"\nPer-game stats:")
        for gn, st in sorted(game_stats.items()):
            total = st["ok"] + st["fail"]
            print(f"  {gn}: {st['ok']}/{total} ({st['ok']*100//max(total,1)}%)")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
