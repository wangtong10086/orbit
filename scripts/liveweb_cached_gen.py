#!/usr/bin/env python3
"""LIVEWEB cached generation — uses pre-cached pages to avoid real API hits.

Injects cache into Docker container before running eval.
Targets underrepresented plugins: hackernews, taostats.

Usage on GPU machine:
    # Extract cache first
    cd /root && tar xzf liveweb_cache.tar.gz

    # Generate hackernews data
    python3 liveweb_cached_gen.py 20 /root/liveweb_hn_cached.jsonl hackernews

    # Generate taostats data
    python3 liveweb_cached_gen.py 20 /root/liveweb_ts_cached.jsonl taostats
"""

import asyncio
import json
import os
import subprocess
import sys
import time

IMAGE = "affinefoundation/liveweb-arena:latest"

COUNT = int(sys.argv[1]) if len(sys.argv) > 1 else 5
OUTPUT = sys.argv[2] if len(sys.argv) > 2 else "/root/liveweb_cached.jsonl"
PLUGIN = sys.argv[3] if len(sys.argv) > 3 else None
START_SEED = int(sys.argv[4]) if len(sys.argv) > 4 else 60000
CACHE_DIR = os.environ.get("CACHE_DIR", "/root/cache")

api_key = os.environ.get("OPENAI_API_KEY", "")
base_url = os.environ.get("OPENAI_BASE_URL", "")
model = os.environ.get("LLM_MODEL", "gpt-5.4")

import affinetes as af

env_vars = {
    "API_KEY": api_key,
    "API_BASE_URL": base_url,
    "LIVEWEB_VERBOSE": "true",
}

# Plugin-specific API keys
taostats_key = os.environ.get("TAOSTATS_API_KEY", "")
if taostats_key:
    env_vars["TAOSTATS_API_KEY"] = taostats_key
coingecko_key = os.environ.get("COINGECKO_API_KEY", "")
if coingecko_key:
    env_vars["COINGECKO_API_KEY"] = coingecko_key

# Validator: use Chutes if available
chutes_key = os.environ.get("CHUTES_API_KEY", "")
if chutes_key:
    env_vars["VALIDATOR_API_KEY"] = chutes_key
    env_vars["VALIDATOR_BASE_URL"] = "https://llm.chutes.ai/v1"
    env_vars["VALIDATION_MODELS"] = "deepseek-ai/DeepSeek-V3.1-TEE,Qwen/Qwen3-32B-TEE"


async def main():
    plugin_str = PLUGIN or "random"
    print(f"LIVEWEB cached gen: {COUNT} tasks, plugin={plugin_str}, model={model}")
    print(f"Cache: {CACHE_DIR}")
    print(f"Output: {OUTPUT}")

    # Kill any existing liveweb container
    subprocess.run(["docker", "rm", "-f", "liveweb-arena-latest"], capture_output=True)

    env = af.load_env(
        image=IMAGE,
        mode="docker",
        env_vars=env_vars,
        pull=False,
        enable_logging=True,
    )
    print("Container started")

    # Find container and inject cache + patches
    import docker
    dc = docker.from_env()
    clist = [c for c in dc.containers.list() if "liveweb" in c.name.lower()]
    if clist:
        cname = clist[0].name

        # Inject cache into container at correct path
        # CacheManager uses /var/lib/liveweb-arena/cache/ (NOT /app/cache/)
        cache_target = "/var/lib/liveweb-arena/cache"
        if os.path.isdir(CACHE_DIR):
            print(f"Injecting cache from {CACHE_DIR} → {cache_target}...")
            # Use tar to reliably copy all dirs (docker cp can silently fail)
            tar_path = "/tmp/lw_cache_inject.tar"
            subprocess.run(
                ["tar", "cf", tar_path, "-C", CACHE_DIR, "."],
                check=True,
            )
            subprocess.run(
                ["docker", "cp", tar_path, f"{cname}:/tmp/lw_cache.tar"],
                check=True,
            )
            subprocess.run(
                ["docker", "exec", cname, "bash", "-c",
                 f"cd {cache_target} && tar xf /tmp/lw_cache.tar && rm /tmp/lw_cache.tar"],
                check=True,
            )
            os.remove(tar_path)
            # Verify
            result = subprocess.run(
                ["docker", "exec", cname, "find", cache_target, "-name", "page.json"],
                capture_output=True, text=True,
            )
            count = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0
            print(f"Cache injected: {count} cached pages")

        # Apply patches if available
        patches = [
            ("/root/llm_client_fixed.py", "/app/liveweb_arena/utils/llm_client.py"),
            ("/root/agent_protocol_fixed.py", "/app/liveweb_arena/core/agent_protocol.py"),
            ("/root/env_fixed.py", "/app/env.py"),
        ]
        patched = 0
        for src, dst in patches:
            if os.path.exists(src):
                subprocess.run(["docker", "cp", src, f"{cname}:{dst}"], check=False)
                patched += 1
        if patched:
            subprocess.run(["docker", "restart", cname], check=True)
            print(f"Patched {patched} files + restarted")
            time.sleep(8)

    success = 0
    failed = 0

    for i in range(COUNT):
        seed = START_SEED + i
        print(f"[{i+1}/{COUNT}] seed={seed} plugin={plugin_str}", end=" ", flush=True)

        try:
            eval_kwargs = {
                "model": model,
                "base_url": base_url,
                "seed": seed,
                "num_subtasks": 1,
                "timeout": 180,
                "_timeout": 240,
            }
            if PLUGIN:
                eval_kwargs["templates"] = [(PLUGIN, None, None)]

            result = await asyncio.wait_for(
                env.evaluate(**eval_kwargs),
                timeout=300,
            )

            score = result.get("score", 0)
            error = result.get("error")
            conv = result.get("extra", {}).get("conversation", [])
            tc = sum(len(str(m.get("content", "") or "")) for m in conv)

            if conv and len(conv) > 2:
                # Check for stop action
                has_stop = any(
                    tc_item.get("function", {}).get("name") == "stop"
                    for msg in conv
                    for tc_item in (msg.get("tool_calls") or [])
                    if isinstance(tc_item, dict)
                )

                # Only keep clean data: must have stop action, score > 0, no errors
                if has_stop and score > 0 and not error:
                    record = {
                        "messages": conv,
                        "env": "LIVEWEB",
                        "source": "cached_eval_distill",
                        "distill_model": model,
                        "score": score,
                        "seed": seed,
                        "plugin": plugin_str,
                        "total_chars": tc,
                    }
                    with open(OUTPUT, "a") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    success += 1
                    err_note = " (validator err)" if error else ""
                    print(f"score={score:.2f} msgs={len(conv)} ~{tc//4}tok{err_note}")
                else:
                    failed += 1
                    print(f"no_stop score={score:.2f}")
            else:
                failed += 1
                print(f"FAIL: {str(error or 'empty conv')[:120]}")

        except asyncio.TimeoutError:
            failed += 1
            print("TIMEOUT")
        except Exception as e:
            failed += 1
            print(f"{type(e).__name__}: {str(e)[:100]}")

    await env.cleanup()
    print(f"\nDone: {success} success / {failed} failed")
    if success > 0:
        print(f"Output: {OUTPUT} ({success} entries)")


if __name__ == "__main__":
    asyncio.run(main())
