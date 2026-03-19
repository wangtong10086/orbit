#!/usr/bin/env python3
"""Run on GPU machine: generate LIVEWEB data via Docker + Claude agent.

Usage: python3 liveweb_gpu_gen.py [count] [output]
Requires env vars: ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, CHUTES_API_KEY
"""
import asyncio
import json
import os
import sys

import affinetes as af

IMAGE = "affinefoundation/liveweb-arena:latest"
MODEL = "claude-sonnet-4-20250514"
COUNT = int(sys.argv[1]) if len(sys.argv) > 1 else 3
OUTPUT = sys.argv[2] if len(sys.argv) > 2 else "/root/liveweb_claude.jsonl"

api_key = os.environ.get("ANTHROPIC_API_KEY", "")
base_url = os.environ.get("ANTHROPIC_BASE_URL", "")
chutes_key = os.environ.get("CHUTES_API_KEY", "")

env_vars = {
    "API_KEY": api_key,
    "API_BASE_URL": base_url + "/v1",
    "VALIDATOR_API_KEY": chutes_key,
    "VALIDATOR_BASE_URL": "https://llm.chutes.ai/v1",
    "LIVEWEB_VERBOSE": "true",
}


async def main():
    print(f"LIVEWEB generation: {COUNT} tasks, model={MODEL}")
    print(f"Output: {OUTPUT}")

    env = af.load_env(image=IMAGE, mode="docker", env_vars=env_vars, pull=False, enable_logging=True)
    print("Container ready")

    success = 0
    failed = 0

    for i in range(COUNT):
        seed = 20000 + i
        print(f"[{i+1}/{COUNT}] seed={seed}", end=" ", flush=True)
        try:
            result = await asyncio.wait_for(
                env.evaluate(
                    model=MODEL,
                    base_url=base_url + "/v1",
                    seed=seed,
                    num_subtasks=1,
                    timeout=180,
                    _timeout=240,
                ),
                timeout=300,
            )
            score = result.get("score", 0)
            error = result.get("error")
            conv = result.get("extra", {}).get("conversation", [])

            if error:
                failed += 1
                err_str = str(error)[:200]
                print(f"ERROR: {err_str}")
            else:
                total_chars = sum(len(str(m.get("content", "") or "")) for m in conv)
                tok = total_chars // 4
                print(f"score={score:.2f} msgs={len(conv)} ~{tok}tok")
                record = {
                    "messages": conv,
                    "env": "LIVEWEB",
                    "source": "claude_docker_eval",
                    "distill_model": MODEL,
                    "score": score,
                    "seed": seed,
                }
                with open(OUTPUT, "a") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                success += 1

        except asyncio.TimeoutError:
            failed += 1
            print("TIMEOUT")
        except Exception as e:
            failed += 1
            print(f"EXCEPTION: {type(e).__name__}: {e}")

    await env.cleanup()
    print(f"\nDone: {success} success, {failed} failed")


asyncio.run(main())
