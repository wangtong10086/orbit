#!/usr/bin/env python3
"""Systematic multi-environment evaluation script — based on affinetes SDK, supports concurrency.

Usage:
  python3 scripts/eval_envs.py --base-url http://172.17.0.1:30000/v1 --samples 100
  python3 scripts/eval_envs.py --base-url http://172.17.0.1:30000/v1 --envs GAME NAVWORLD --samples 50 --concurrency 4
"""

import asyncio
import argparse
import json
import os
import sys
import time
import random
from pathlib import Path

import affinetes as af

# ============================================================
# Environment configuration — timeout matching production (2h=7200s)
# ============================================================
ENV_CONFIGS = {
    "GAME": {
        "env_path": "environments/openspiel",
        "image_tag": "openspiel:eval",
        "env_vars_keys": [],
        "eval_defaults": {
            "timeout": 7200,
            "temperature": 0,
        },
        "mem_limit": "2g",
        # Real eval range: [[0, 500M], [600M, 800M]] → idx 0-4 and 6-7
        # goofspiel=0, liars_dice=1, leduc_poker=2, gin_rummy=3,
        # othello=4, hex=6, clobber=7
        # EXCLUDED: backgammon=5 (not in eval range), hearts=8, euchre=9 (>800M)
        "eval_game_indices": [0, 1, 2, 3, 4, 6, 7],
    },
    "NAVWORLD": {
        "env_path": "environments/qqr",
        "image_tag": "qqr:eval",
        "env_vars_keys": ["AMAP_MAPS_API_KEY", "AMAP_API_KEY"],
        "eval_defaults": {
            "timeout": 7200,
            "temperature": 0,
        },
        "mem_limit": "2g",
    },
    "LGC-v2": {
        "env_path": "environments/primeintellect/lgc-v2",
        "image_tag": "lgc-v2:eval",
        "env_vars_keys": [],
        "eval_defaults": {"timeout": 7200},
        "mem_limit": "1g",
    },
    "PRINT": {
        "env_path": "environments/trace",
        "image_tag": "trace:eval",
        "env_vars_keys": [],
        "eval_defaults": {"timeout": 7200},
        "mem_limit": "1g",
    },
    "SWE-SYNTH": {
        "env_path": "environments/SWE-SYNTH",
        "image_tag": "swe-synth:eval",
        "env_vars_keys": [],
        "eval_defaults": {"timeout": 7200},
        "mem_limit": "4g",
        "volumes": {"/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"}},
    },
    "LIVEWEB": {
        "env_path": None,
        "image_tag": "affinefoundation/liveweb-arena:latest",
        "env_vars_keys": ["TAOSTATS_API_KEY"],
        "max_task_id": 107000000,
        "eval_defaults": {"timeout": 7200, "temperature": 0},
        "mem_limit": "2g",
        "pull": True,
        "volumes": {"/var/lib/liveweb-arena/cache": {"bind": "/var/lib/liveweb-arena/cache", "mode": "rw"}},
        "extra_env": {"LIVEWEB_CACHE_TTL": "999999999"},
        "cached_task_ids": "data/liveweb_cached_task_ids.json",
    },
}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def generate_task_ids(cfg, rng, samples):
    """Generate task_ids, uniformly distributed across eval games for GAME env."""
    eval_indices = cfg.get("eval_game_indices")
    max_task_id = cfg.get("max_task_id", 2**31 - 1)
    cached_ids_file = cfg.get("cached_task_ids")

    task_ids = []
    if cached_ids_file:
        # Use fixed cached task IDs (e.g., LIVEWEB with pre-verified cache coverage)
        cached = json.load(open(cached_ids_file))
        task_ids = rng.sample(cached, min(samples, len(cached)))
        if len(task_ids) < samples:
            log(f"WARNING: only {len(cached)} cached IDs, requested {samples}")
    elif eval_indices:
        # GAME: distribute samples uniformly across all eval games
        n_games = len(eval_indices)
        for i in range(samples):
            game_idx = eval_indices[i % n_games]
            config_id = rng.randint(0, 99_999_999)
            task_id = game_idx * 100_000_000 + config_id
            task_ids.append(task_id)
        # Shuffle so games interleave (better for concurrent eval)
        rng.shuffle(task_ids)
    else:
        for _ in range(samples):
            task_id = rng.randint(1, max_task_id)
            task_ids.append(task_id)
    return task_ids


async def eval_single(env, env_name, model, base_url, task_id, seed, cfg, idx, total):
    """Evaluate a single sample."""
    eval_params = {
        "model": model,
        "base_url": base_url,
        "task_id": task_id,
        "seed": seed,
        **cfg["eval_defaults"],
    }

    t0 = time.time()
    try:
        result = await env.evaluate(**eval_params)
        elapsed = time.time() - t0
        score = float(result.get("score", 0.0))
        error = result.get("error")

        if error:
            log(f"  [{idx+1}/{total}] task={task_id}: ERROR {error} ({elapsed:.1f}s)")
        else:
            log(f"  [{idx+1}/{total}] task={task_id}: score={score:.2f} ({elapsed:.1f}s)")

        return {"index": idx, "task_id": task_id, "seed": seed, "score": score,
                "error": error, "elapsed": elapsed, "raw": result}
    except Exception as e:
        elapsed = time.time() - t0
        log(f"  [{idx+1}/{total}] task={task_id}: EXCEPTION {e} ({elapsed:.1f}s)")
        return {"index": idx, "task_id": task_id, "seed": seed, "score": 0.0,
                "error": str(e), "elapsed": elapsed}


async def evaluate_env(env_name, model, base_url, api_key, samples, seed, output_dir, concurrency):
    """Evaluate a single environment with concurrency."""
    cfg = ENV_CONFIGS[env_name]
    rng = random.Random(seed)

    # Prepare environment variables
    env_vars = {"CHUTES_API_KEY": api_key}
    for key in cfg.get("env_vars_keys", []):
        val = os.environ.get(key, "")
        if val:
            env_vars[key] = val
        else:
            log(f"[{env_name}] WARNING: {key} not set")
    env_vars.update(cfg.get("extra_env", {}))

    # Loading environment with multiple replicas for parallel eval
    # host_network=True causes port conflicts with replicas > 1, so use bridge mode
    replicas = min(concurrency, 8)  # Up to 8 container replicas
    use_host_network = (replicas == 1)
    log(f"[{env_name}] Loading environment {cfg['image_tag']} (replicas={replicas}, host_net={use_host_network})...")
    load_kwargs = {
        "image": cfg["image_tag"], "mode": "docker", "env_vars": env_vars,
        "host_network": use_host_network, "mem_limit": cfg.get("mem_limit", "2g"),
        "replicas": replicas, "load_balance": "round_robin",
    }
    if cfg.get("pull"):
        load_kwargs["pull"] = True
    if cfg.get("volumes"):
        load_kwargs["volumes"] = cfg["volumes"]

    env = af.load_env(**load_kwargs)
    log(f"[{env_name}] Environment ready (concurrency={concurrency}, replicas={replicas})")

    # Generate task_ids
    task_ids = generate_task_ids(cfg, rng, samples)
    seeds = [rng.randint(0, 2**32 - 1) for _ in range(samples)]

    # Incremental save path (JSONL, one result per line as completed)
    os.makedirs(output_dir, exist_ok=True)
    incremental_path = os.path.join(output_dir, f"eval_{env_name.lower().replace('-', '_')}_incremental.jsonl")
    with open(incremental_path, "w") as f:
        pass  # truncate

    # Concurrent evaluation with incremental save
    semaphore = asyncio.Semaphore(concurrency)
    results_lock = asyncio.Lock()

    async def run_with_sem(idx):
        async with semaphore:
            result = await eval_single(env, env_name, model, base_url,
                                       task_ids[idx], seeds[idx], cfg, idx, samples)
            # Save immediately after each task completes
            async with results_lock:
                with open(incremental_path, "a") as f:
                    f.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
            return result

    tasks = [run_with_sem(i) for i in range(samples)]
    results = await asyncio.gather(*tasks)

    await env.cleanup()

    # Summary
    errors = sum(1 for r in results if r.get("error"))
    total_score = sum(r["score"] for r in results)
    mean_score = total_score / samples if samples > 0 else 0.0
    valid = [r for r in results if not r.get("error")]

    summary = {
        "env": env_name, "model": model, "samples": samples, "errors": errors,
        "mean_score": mean_score, "valid_count": len(valid),
        "valid_mean": total_score / len(valid) if valid else 0.0,
        "results": sorted(results, key=lambda r: r["index"]),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"eval_{env_name.lower().replace('-', '_')}.json")
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    log(f"[{env_name}] Results saved to {out_path}")

    return summary


async def build_images(affinetes_dir, envs):
    for env_name in envs:
        cfg = ENV_CONFIGS[env_name]
        if cfg.get("pull") or cfg["env_path"] is None:
            log(f"[{env_name}] Using pre-built image {cfg['image_tag']}")
            continue
        env_path = os.path.join(affinetes_dir, cfg["env_path"])
        if not os.path.isdir(env_path):
            log(f"[{env_name}] WARNING: Environment directory not found: {env_path}")
            continue
        log(f"[{env_name}] Building image {cfg['image_tag']}...")
        af.build_image_from_env(env_path=env_path, image_tag=cfg["image_tag"], quiet=True)
        log(f"[{env_name}] Image build complete")


async def main():
    parser = argparse.ArgumentParser(description="Affine multi-environment evaluation")
    parser.add_argument("--base-url", default="http://172.17.0.1:30000/v1", help="sglang API base URL (Docker bridge)")
    parser.add_argument("--model", default="default", help="Model name")
    parser.add_argument("--envs", nargs="+", default=["GAME", "NAVWORLD", "LIVEWEB"],
                        help="Environments to evaluate")
    parser.add_argument("--samples", type=int, default=100, help="Samples per environment")
    parser.add_argument("--concurrency", type=int, default=5, help="Concurrency per environment")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--output-dir", default="/root/logs", help="Output directory")
    parser.add_argument("--affinetes-dir", default="/root/affinetes", help="affinetes repo path")
    parser.add_argument("--skip-build", action="store_true", help="Skip image build")
    parser.add_argument("--api-key", default=None, help="API key")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("CHUTES_API_KEY", "dummy-local")

    for e in args.envs:
        if e not in ENV_CONFIGS:
            print(f"Unknown environment: {e}. Available: {list(ENV_CONFIGS.keys())}")
            sys.exit(1)

    log("=" * 60)
    log("Affine Forge multi-environment evaluation")
    log(f"Model: {args.model}")
    log(f"Base URL: {args.base_url}")
    log(f"Environments: {args.envs}")
    log(f"Samples per env: {args.samples}, concurrency: {args.concurrency}")
    log(f"Timeout: matching production (7200s)")
    log("=" * 60)

    if not args.skip_build:
        await build_images(args.affinetes_dir, args.envs)

    all_summaries = {}
    for env_name in args.envs:
        log(f"\n{'='*60}")
        log(f"Evaluating {env_name} ({args.samples} samples, concurrency={args.concurrency})")
        log(f"{'='*60}")
        try:
            summary = await evaluate_env(
                env_name, args.model, args.base_url, api_key,
                args.samples, args.seed, args.output_dir, args.concurrency,
            )
            all_summaries[env_name] = {
                "mean_score": summary["mean_score"],
                "errors": summary["errors"],
                "samples": summary["samples"],
            }
        except Exception as e:
            log(f"[{env_name}] Evaluation failed: {e}")
            import traceback
            traceback.print_exc()
            all_summaries[env_name] = {"error": str(e)}

    log(f"\n{'='*60}")
    log("Evaluation summary")
    log(f"{'='*60}")
    for env_name, s in all_summaries.items():
        if "error" in s:
            log(f"  {env_name:12s}: FAILED - {s['error']}")
        else:
            log(f"  {env_name:12s}: mean={s['mean_score']:.4f}, errors={s['errors']}/{s['samples']}")

    summary_path = os.path.join(args.output_dir, "eval_summary.json")
    with open(summary_path, "w") as f:
        json.dump({"model": args.model, "base_url": args.base_url,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "results": all_summaries}, f, indent=2)
    log(f"Summary saved to {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
