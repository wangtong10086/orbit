#!/usr/bin/env python3
"""Generate LIVEWEB training data using real liveweb-arena container + Claude as agent.

Runs on GPU machine with Docker. Uses affinetes SDK to:
1. Start liveweb-arena container
2. Run eval tasks with Claude Sonnet as the agent (via custom API endpoint)
3. Capture full trajectories with tool_calls in correct eval format
4. Filter by score and length

Usage (on GPU machine):
    python3 /root/liveweb_real_gen.py -n 5 -o /root/liveweb_claude_real.jsonl
"""

import asyncio
import argparse
import json
import os
import sys

# API config: support multiple providers via env vars or --model/--base-url/--api-key args
# Default: OpenAI-compatible endpoint (codex proxy with gpt-5.4 model name)
DEFAULT_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("QWEN_API_KEY") or os.getenv("ANTHROPIC_API_KEY", "")
DEFAULT_BASE_URL = os.getenv("OPENAI_BASE_URL") or os.getenv("QWEN_BASE_URL", "https://dashscope-us.aliyuncs.com/compatible-mode/v1")
DEFAULT_MODEL = os.getenv("LLM_MODEL", "gpt-5.4")

IMAGE = "affinefoundation/liveweb-arena:latest"


def parse_args():
    parser = argparse.ArgumentParser(description="LIVEWEB trajectory generation via real eval environment")
    parser.add_argument("-n", "--count", type=int, default=5, help="Number of tasks to run")
    parser.add_argument("-o", "--output", default="/root/liveweb_gen_out.jsonl", help="Output file")
    parser.add_argument("--min-score", type=float, default=0.3, help="Minimum score to keep")
    parser.add_argument("--max-chars", type=int, default=32000, help="Max chars per entry")
    parser.add_argument("--start-seed", type=int, default=10000, help="Starting seed")
    parser.add_argument("--timeout", type=int, default=300, help="Per-task timeout seconds")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="LLM model name")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="OpenAI-compatible base URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="API key")
    parser.add_argument("--plugin", default=None, help="Target specific plugin (e.g. hackernews, taostats, coingecko)")
    parser.add_argument("--num-subtasks", type=int, default=1, help="Number of subtasks per task")
    return parser.parse_args()


def extract_sft_record(result: dict, seed: int, model: str) -> dict | None:
    """Extract SFT training record preserving full tool_calls.

    Saves trajectories where agent completed (has stop action) even if
    validator failed (e.g. Chutes model 404). Score will be 0 for
    unvalidated entries — caller should filter or manually review.
    """
    conversation = result.get("extra", {}).get("conversation", [])
    if not conversation:
        return None

    # Check if agent actually completed (has a stop tool_call)
    has_stop = False
    for msg in conversation:
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                if isinstance(tc, dict) and tc.get("function", {}).get("name") == "stop":
                    has_stop = True
                    break

    if not has_stop:
        return None

    total_chars = sum(len(str(m.get("content", "") or "")) for m in conversation)

    return {
        "messages": conversation,
        "env": "LIVEWEB",
        "source": "real_eval_distill",
        "distill_model": model,
        "score": result.get("score", 0),
        "seed": seed,
        "total_chars": total_chars,
        "validator_ok": not bool(result.get("error")),
    }


async def main():
    args = parse_args()

    import affinetes as af

    api_key = args.api_key
    base_url = args.base_url
    model = args.model

    # Need API keys for plugins
    taostats_key = os.getenv("TAOSTATS_API_KEY", "")
    coingecko_key = os.getenv("COINGECKO_API_KEY", "")

    env_vars = {
        "API_KEY": api_key,
        "API_BASE_URL": base_url,
        # No VALIDATOR_API_KEY — use same LLM (qwen3-max) for validation
        # Chutes validator models are all 404, causing crashes
        "LIVEWEB_VERBOSE": "true",
    }
    if taostats_key:
        env_vars["TAOSTATS_API_KEY"] = taostats_key
    if coingecko_key:
        env_vars["COINGECKO_API_KEY"] = coingecko_key

    print(f"LIVEWEB trajectory generation")
    print(f"  Count: {args.count}")
    print(f"  Model: {model}")
    print(f"  Base URL: {base_url}")
    print(f"  Plugin: {args.plugin or 'random'}")
    print(f"  Subtasks: {args.num_subtasks}")
    print(f"  Min score: {args.min_score}")
    print(f"  Output: {args.output}")

    print("\nLoading liveweb-arena container...")
    env = af.load_env(
        image=IMAGE,
        mode="docker",
        env_vars=env_vars,
        pull=False,
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
                eval_kwargs = {
                    "model": model,
                    "base_url": base_url,
                    "seed": seed,
                    "num_subtasks": args.num_subtasks,
                    "timeout": args.timeout,
                    "_timeout": args.timeout + 60,
                }
                # Target specific plugin if requested
                if args.plugin:
                    eval_kwargs["templates"] = [(args.plugin, None, None)]

                result = await asyncio.wait_for(
                    env.evaluate(**eval_kwargs),
                    timeout=args.timeout + 120,
                )

                score = result.get("score", 0)
                error = result.get("error")
                conv = result.get("extra", {}).get("conversation", [])
                total_chars = sum(len(str(m.get("content", "") or "")) for m in conv)

                # Try to extract record (even if validator failed)
                record = extract_sft_record(result, seed, model)

                if record and total_chars <= args.max_chars:
                    # Agent completed (has stop action)
                    if error and "validator" in str(error).lower():
                        # Validator failed but agent completed — save anyway
                        with open(args.output, "a") as f:
                            f.write(json.dumps(record, ensure_ascii=False) + "\n")
                        success += 1
                        print(f"✓ score=? (validator down) msgs={len(conv)} ~{total_chars//4}tok")
                    elif score >= args.min_score:
                        with open(args.output, "a") as f:
                            f.write(json.dumps(record, ensure_ascii=False) + "\n")
                        success += 1
                        print(f"✓ score={score:.2f} msgs={len(conv)} ~{total_chars//4}tok")
                    else:
                        filtered += 1
                        print(f"✗ filtered (score={score:.2f})")
                elif error:
                    failed += 1
                    print(f"✗ error: {str(error)[:80]}")
                else:
                    filtered += 1
                    reason = "no stop action" if not record else f"~{total_chars//4}tok"
                    print(f"✗ filtered ({reason})")

            except asyncio.TimeoutError:
                failed += 1
                print("✗ timeout")
            except Exception as e:
                failed += 1
                print(f"✗ {type(e).__name__}: {str(e)[:100]}")

    finally:
        await env.cleanup()

    print(f"\n{'='*60}")
    print(f"Done: {success} success / {filtered} filtered / {failed} failed")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
