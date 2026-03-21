#!/usr/bin/env python3
"""LIVEWEB training data generator — systematic pipeline.

Uses liveweb-arena's native trajectory export with compression.
Runs on GPU machine with Docker + affinetes SDK.

Architecture:
  Agent LLM:     Claude Sonnet via claudecode proxy (best browser agent)
  Validator LLM: Chutes API (separate endpoint, won't compete with agent)
  Compression:   liveweb-arena's compress_conversation (level 3)
  Export:        liveweb-arena's build_sft_record (standard format)

Usage:
    # Single plugin, 20 tasks
    python3 liveweb_real_gen.py -n 20 --plugin coingecko -o /root/liveweb_cg.jsonl

    # All plugins, batch
    for p in coingecko stooq taostats hackernews openlibrary arxiv openmeteo; do
        python3 liveweb_real_gen.py -n 15 --plugin $p -o /root/liveweb_all.jsonl
    done
"""

import asyncio
import argparse
import json
import os
import sys

# Default API config from env
DEFAULT_API_KEY = os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY", "")
DEFAULT_BASE_URL = os.getenv("ANTHROPIC_BASE_URL") or os.getenv("OPENAI_BASE_URL", "")
DEFAULT_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")

IMAGE = "affinefoundation/liveweb-arena:latest"


def parse_args():
    parser = argparse.ArgumentParser(description="LIVEWEB trajectory generation with compression")
    parser.add_argument("-n", "--count", type=int, default=5, help="Number of tasks to run")
    parser.add_argument("-o", "--output", default="/root/liveweb_gen_out.jsonl", help="Output JSONL file (append mode)")
    parser.add_argument("--start-seed", type=int, default=10000, help="Starting seed")
    parser.add_argument("--timeout", type=int, default=300, help="Per-task timeout seconds")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Agent LLM model name")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Agent LLM base URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="Agent LLM API key")
    parser.add_argument("--plugin", default=None, help="Target specific plugin (coingecko/stooq/taostats/hackernews/openlibrary/arxiv/openmeteo)")
    parser.add_argument("--num-subtasks", type=int, default=1, help="Subtasks per task (1=simple, 2=eval-like)")
    parser.add_argument("--compression", type=int, default=3, choices=[0, 1, 2, 3], help="Compression level (0=none, 3=max)")
    parser.add_argument("--max-tree-chars", type=int, default=4000, help="Max chars per accessibility tree after compression")
    parser.add_argument("--max-total-chars", type=int, default=48000, help="Max total chars per trajectory (post-compression)")
    parser.add_argument("--min-score", type=float, default=0.0, help="Minimum score to keep (0=keep all completed)")
    parser.add_argument("--save-failed", action="store_true", help="Save trajectories even if agent didn't complete (for GRPO)")
    return parser.parse_args()


def compress_and_export(result: dict, args, seed: int) -> dict | None:
    """Use liveweb-arena's native compression and export."""
    try:
        from liveweb_arena.training.compression import compress_conversation
    except ImportError:
        # Fallback: no compression available
        return _fallback_export(result, args, seed)

    conversation = result.get("extra", {}).get("conversation", [])
    if not conversation:
        return None

    # Check if agent completed (has stop action)
    has_stop = any(
        tc.get("function", {}).get("name") == "stop"
        for msg in conversation
        for tc in (msg.get("tool_calls") or [])
        if isinstance(tc, dict)
    )
    if not has_stop and not args.save_failed:
        return None

    # Apply liveweb-arena compression
    compressed = compress_conversation(conversation, args.compression, args.max_tree_chars)

    total_chars = sum(len(str(m.get("content", "") or "")) for m in compressed)
    if total_chars > args.max_total_chars:
        return None

    original_chars = sum(len(str(m.get("content", "") or "")) for m in conversation)

    return {
        "messages": compressed,
        "env": "LIVEWEB",
        "source": "real_eval_distill",
        "distill_model": args.model,
        "score": result.get("score", 0),
        "seed": seed,
        "total_chars": total_chars,
        "original_chars": original_chars,
        "compression_ratio": round(total_chars / max(original_chars, 1), 2),
        "compression_level": args.compression,
        "has_stop": has_stop,
        "validator_ok": not bool(result.get("error")),
    }


def _fallback_export(result: dict, args, seed: int) -> dict | None:
    """Fallback when liveweb_arena.training not importable."""
    conversation = result.get("extra", {}).get("conversation", [])
    if not conversation:
        return None

    has_stop = any(
        tc.get("function", {}).get("name") == "stop"
        for msg in conversation
        for tc in (msg.get("tool_calls") or [])
        if isinstance(tc, dict)
    )
    if not has_stop and not args.save_failed:
        return None

    total_chars = sum(len(str(m.get("content", "") or "")) for m in conversation)
    if total_chars > args.max_total_chars:
        return None

    return {
        "messages": conversation,
        "env": "LIVEWEB",
        "source": "real_eval_distill",
        "distill_model": args.model,
        "score": result.get("score", 0),
        "seed": seed,
        "total_chars": total_chars,
        "compression_level": 0,
        "has_stop": has_stop,
        "validator_ok": not bool(result.get("error")),
    }


async def main():
    args = parse_args()

    import affinetes as af

    api_key = args.api_key
    base_url = args.base_url
    model = args.model

    # Plugin API keys
    taostats_key = os.getenv("TAOSTATS_API_KEY", "")
    coingecko_key = os.getenv("COINGECKO_API_KEY", "")

    # Validator: use same endpoint. Model names depend on provider.
    val_models = os.getenv("VALIDATION_MODELS", "")
    if not val_models:
        if "chutes" in base_url.lower():
            val_models = "deepseek-ai/DeepSeek-V3.1-TEE,Qwen/Qwen3-32B-TEE"
        else:
            val_models = "claude-sonnet-4-20250514,claude-3-haiku-20240307"
    env_vars = {
        "API_KEY": api_key,
        "API_BASE_URL": base_url,
        "VALIDATION_MODELS": val_models,
        "LIVEWEB_VERBOSE": "true",
    }
    if taostats_key:
        env_vars["TAOSTATS_API_KEY"] = taostats_key
    if coingecko_key:
        env_vars["COINGECKO_API_KEY"] = coingecko_key

    print(f"LIVEWEB trajectory generation")
    print(f"  Agent:       {model} @ {base_url[:50]}...")
    print(f"  Validator:   same endpoint (Claude models)")
    print(f"  Plugin:      {args.plugin or 'random'}")
    print(f"  Subtasks:    {args.num_subtasks}")
    print(f"  Compression: level {args.compression} (max_tree={args.max_tree_chars})")
    print(f"  Count:       {args.count}")
    print(f"  Output:      {args.output}")

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
                if args.plugin:
                    eval_kwargs["templates"] = [(args.plugin, None, None)]

                result = await asyncio.wait_for(
                    env.evaluate(**eval_kwargs),
                    timeout=args.timeout + 120,
                )

                # Use native compression + export
                record = compress_and_export(result, args, seed)
                score = result.get("score", 0)
                error = result.get("error")

                if record:
                    if score >= args.min_score or (error and record.get("has_stop")):
                        with open(args.output, "a") as f:
                            f.write(json.dumps(record, ensure_ascii=False) + "\n")
                        success += 1
                        ratio = record.get("compression_ratio", 1.0)
                        chars = record["total_chars"]
                        print(f"✓ score={score:.2f} ~{chars//4}tok compress={ratio:.0%}")
                    else:
                        filtered += 1
                        print(f"✗ filtered (score={score:.2f})")
                elif error:
                    failed += 1
                    print(f"✗ error: {str(error)[:80]}")
                else:
                    filtered += 1
                    print("✗ filtered (no stop / too long)")

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
    if success > 0:
        print(f"Output: {args.output} ({success} entries)")


if __name__ == "__main__":
    asyncio.run(main())
