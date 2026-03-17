#!/usr/bin/env python3
"""
LIVEWEB short-trajectory distillation data generator

Uses affinetes SDK to run LIVEWEB container with num_subtasks=1 for short trajectories.
Requires Docker environment and TAOSTATS_API_KEY.

Usage:
    # Small batch validation (5 samples)
    python3 scripts/liveweb_gen.py -n 5 --min-score 0.3 -o data/liveweb_test.jsonl

    # Easy template batch
    python3 scripts/liveweb_gen.py -n 50 --min-score 0.5 -o data/liveweb_gen.jsonl
"""

import asyncio
import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"), override=True)

import affinetes as af

IMAGE = "affinefoundation/liveweb-arena:latest"
PATCHED_ENV_PY = str(Path(__file__).parent / "liveweb_env_patched.py")
CACHE_DIR = "/var/lib/liveweb-arena/cache"


def parse_args():
    parser = argparse.ArgumentParser(description="LIVEWEB distillation data generation")
    parser.add_argument("-n", "--count", type=int, default=5, help="Number of samples")
    parser.add_argument("-o", "--output", default="data/liveweb_gen.jsonl", help="Output file")
    parser.add_argument("--model", default="qwen3-max", help="LLM model")
    parser.add_argument("--base-url", default="https://dashscope-us.aliyuncs.com/compatible-mode/v1", help="API URL")
    parser.add_argument("--min-score", type=float, default=0.5, help="Minimum score")
    parser.add_argument("--max-chars", type=int, default=64000, help="Max characters (~16K tokens)")
    parser.add_argument("--timeout", type=int, default=600, help="Per-task timeout seconds")
    parser.add_argument("--start-seed", type=int, default=50000, help="Starting seed")
    return parser.parse_args()


def extract_sft_record(result: dict, seed: int) -> dict | None:
    """Extract SFT training record from evaluation result"""
    if not result or result.get("error"):
        return None

    conversation = result.get("extra", {}).get("conversation", [])
    if not conversation:
        return None

    clean_msgs = []
    for msg in conversation:
        clean_msg = {"role": msg["role"], "content": msg.get("content") or ""}
        # Preserve tool_calls if present
        if "tool_calls" in msg:
            clean_msg["tool_calls"] = msg["tool_calls"]
        if "tool_call_id" in msg:
            clean_msg["tool_call_id"] = msg["tool_call_id"]
        clean_msgs.append(clean_msg)

    if not clean_msgs or clean_msgs[-1]["role"] != "assistant":
        return None

    return {
        "messages": clean_msgs,
        "env": "LIVEWEB",
        "source": "distillation",
        "distill_model": None,
        "score": result.get("score", 0),
        "seed": seed,
    }


async def main():
    args = parse_args()

    api_key = os.getenv("QWEN_API_KEY") or os.getenv("CHUTES_API_KEY")
    if not api_key:
        print("Error: QWEN_API_KEY or CHUTES_API_KEY not set")
        sys.exit(1)

    taostats_key = os.getenv("TAOSTATS_API_KEY")
    if not taostats_key:
        print("Error: TAOSTATS_API_KEY not set")
        sys.exit(1)

    print(f"LIVEWEB distillation data generation")
    print(f"  Count: {args.count}")
    print(f"  Model: {args.model}")
    print(f"  num_subtasks: 1 (short trajectory)")
    print(f"  Min score: {args.min_score}")
    print(f"  Max chars: {args.max_chars:,} (~{args.max_chars//4:,} tokens)")
    print(f"  Output: {args.output}")
    print()

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    # Agent uses QWEN_API_KEY (DashScope qwen-max)
    # Validator uses separate API (CHUTES_API_KEY, supports validator model list)
    chutes_key = os.getenv("CHUTES_API_KEY")
    if not chutes_key:
        print("Error: CHUTES_API_KEY not set (needed for validator)")
        sys.exit(1)

    env_vars = {
        "API_KEY": api_key,
        "VALIDATOR_API_KEY": chutes_key,
        "VALIDATOR_BASE_URL": "https://llm.chutes.ai/v1",
        "LIVEWEB_VERBOSE": "true",
        "TAOSTATS_API_KEY": taostats_key,
    }
    coingecko_key = os.getenv("COINGECKO_API_KEY")
    if coingecko_key:
        env_vars["COINGECKO_API_KEY"] = coingecko_key

    print("Loading LIVEWEB container...")
    env = af.load_env(
        image=IMAGE,
        mode="docker",
        env_vars=env_vars,
        pull=False,
        volumes={
            CACHE_DIR: {"bind": CACHE_DIR, "mode": "rw"},
            PATCHED_ENV_PY: {"bind": "/app/env.py", "mode": "ro"},
        },
        enable_logging=True,
    )
    print("Container ready\n")

    success = 0
    failed = 0
    filtered = 0

    try:
        for i in range(args.count):
            seed = args.start_seed + i
            print(f"[{i+1}/{args.count}] seed={seed}", end=" ", flush=True)

            try:
                result = await asyncio.wait_for(
                    env.evaluate(
                        model=args.model,
                        base_url=args.base_url,
                        seed=seed,
                        num_subtasks=1,
                        timeout=args.timeout,
                        _timeout=args.timeout + 60,
                    ),
                    timeout=args.timeout + 120,
                )

                score = result.get("score", 0)
                error = result.get("error")
                conv = result.get("extra", {}).get("conversation", [])
                total_chars = sum(len(str(m.get("content", ""))) for m in conv)
                est_tok = total_chars // 4

                if error:
                    failed += 1
                    print(f"✗ error: {str(error)[:80]}")
                elif score >= args.min_score and total_chars <= args.max_chars:
                    record = extract_sft_record(result, seed)
                    if record:
                        record["distill_model"] = args.model
                        with open(args.output, "a") as f:
                            f.write(json.dumps(record, ensure_ascii=False) + "\n")
                        success += 1
                        print(f"✓ score={score:.2f} msgs={len(conv)} ~{est_tok:,}tok")
                    else:
                        filtered += 1
                        print("✗ filtered (format)")
                else:
                    filtered += 1
                    reason = f"score={score:.2f}" if score < args.min_score else f"~{est_tok:,}tok"
                    print(f"✗ filtered ({reason})")

            except asyncio.TimeoutError:
                failed += 1
                print("✗ timeout")
            except Exception as e:
                failed += 1
                print(f"✗ {type(e).__name__}: {str(e)[:100]}")

    finally:
        await env.cleanup()
        print("Container cleaned up")

    print(f"\n{'='*60}")
    print(f"Done: {success} success / {filtered} filtered / {failed} failed (total {args.count})")
    print(f"Success rate: {success*100//max(args.count,1)}%")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
