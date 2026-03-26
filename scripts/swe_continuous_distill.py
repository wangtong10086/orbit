#!/usr/bin/env python3
"""SWE Continuous Distillation Daemon.

Runs on m2. Automatically:
1. Polls R2 for new tasks periodically
2. Filters to Go-only (other languages have ~0% success rate)
3. Deduplicates against all existing outputs + logs
4. Maintains N concurrent workers with auto-restart
5. Prunes completed Docker containers

Usage:
    python3 swe_continuous_distill.py --workers 3 --poll-interval 1800
"""
import json, glob, os, re, sys, time, subprocess, signal, argparse
from collections import defaultdict
from pathlib import Path

# ── Config ──
R2_ACCESS = os.environ.get("R2_ACCESS_KEY_ID", "525c1b593092a9b26c916734a9c344ff")
R2_SECRET = os.environ.get("R2_SECRET_ACCESS_KEY", "d35adb29c7ae4f4a89a6c0a8a6679ebee9c769183b6e5bf2b7297202eaf81bec")
R2_ENDPOINT = "https://af76430a7056e37bd99ee03a4468d893.r2.cloudflarestorage.com"
R2_BUCKET = "affine-swe-infinite-private"

DISTILL_SCRIPT = "/root/swe_distill.py"
WORK_DIR = "/root"
OUTPUT_DIR = "/root"

# Languages worth attempting (others have ~0% success)
VIABLE_LANGUAGES = {"go", "rust"}  # Go ~28%, Rust ~1%

def get_attempted_ids():
    """Collect all attempted instance_ids from outputs + logs."""
    attempted = set()
    success = set()

    # From output files
    for f in glob.glob(f"{OUTPUT_DIR}/real_distill_*.jsonl"):
        for line in open(f):
            try:
                iid = json.loads(line)["instance_id"]
                attempted.add(iid)
                success.add(iid)
            except:
                pass

    # From log files
    for logf in glob.glob(f"{WORK_DIR}/swe_distill_*.log"):
        try:
            for line in open(logf):
                if "Starting" in line:
                    parts = line.split("]")[0].split("[")
                    if len(parts) > 1:
                        attempted.add(parts[1].strip())
                m = re.match(r'\[(?:R?\d+/\d+)\]\s+(\S+)', line)
                if m:
                    attempted.add(m.group(1))
        except:
            pass

    return attempted, success


def fetch_new_tasks(attempted, go_only=True):
    """Fetch unattempted tasks from R2, optionally filtering to Go-only."""
    import boto3
    from botocore.config import Config

    s3 = boto3.client("s3", endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS, aws_secret_access_key=R2_SECRET,
        config=Config(signature_version="s3v4"), region_name="auto")

    pool_keys = []
    for page in s3.get_paginator("list_objects_v2").paginate(
            Bucket=R2_BUCKET, Prefix="", Delimiter="/"):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".json"):
                pool_keys.append(obj["Key"])

    new_tasks = []
    by_lang = defaultdict(int)
    skipped_lang = defaultdict(int)

    for i, key in enumerate(pool_keys):
        try:
            t = json.loads(s3.get_object(Bucket=R2_BUCKET, Key=key)["Body"].read())
            iid = t["instance_id"]
            lang = t.get("repo_language", "unknown").lower()

            if iid in attempted:
                continue

            if go_only and lang not in VIABLE_LANGUAGES:
                skipped_lang[lang] += 1
                continue

            new_tasks.append(t)
            by_lang[lang] += 1
        except:
            pass

        if (i + 1) % 500 == 0:
            print(f"  Scanned {i+1}/{len(pool_keys)}...", flush=True)

    print(f"\nR2 pool: {len(pool_keys)} total")
    print(f"New viable tasks: {len(new_tasks)}")
    for l, c in sorted(by_lang.items(), key=lambda x: -x[1]):
        print(f"  {l}: {c}")
    if skipped_lang:
        print(f"Skipped (non-viable languages):")
        for l, c in sorted(skipped_lang.items(), key=lambda x: -x[1]):
            print(f"  {l}: {c}")

    return new_tasks


def write_batch_files(tasks, num_workers):
    """Split tasks into worker batch files."""
    chunk_size = len(tasks) // num_workers
    batches = []

    for i in range(num_workers):
        start = i * chunk_size
        end = start + chunk_size if i < num_workers - 1 else len(tasks)
        batch_file = f"{WORK_DIR}/swe_batch_daemon_w{i}.jsonl"

        with open(batch_file, "w") as f:
            for t in tasks[start:end]:
                f.write(json.dumps(t) + "\n")

        batches.append({
            "file": batch_file,
            "count": end - start,
            "output": f"{OUTPUT_DIR}/real_distill_daemon_w{i}.jsonl",
            "log": f"{WORK_DIR}/swe_distill_daemon_w{i}.log",
        })
        print(f"  w{i}: {end - start} tasks -> {batch_file}")

    return batches


def launch_worker(batch, model, api_base, api_key):
    """Launch a distillation worker process."""
    cmd = [
        "python3", "-u", DISTILL_SCRIPT,
        "--task-file", batch["file"],
        "--output", batch["output"],
        "--resume", "--local-only",
        "--model", model,
        "--api-base", api_base,
        "--api-key", api_key,
    ]

    log_fh = open(batch["log"], "a")
    proc = subprocess.Popen(cmd, stdout=log_fh, stderr=log_fh, cwd=WORK_DIR)
    batch["proc"] = proc
    batch["log_fh"] = log_fh
    batch["pid"] = proc.pid
    print(f"  Launched worker PID {proc.pid}: {batch['file']}")
    return proc


def check_workers(batches, model, api_base, api_key):
    """Check worker health and restart dead ones."""
    for batch in batches:
        proc = batch.get("proc")
        if proc is None or proc.poll() is not None:
            exit_code = proc.returncode if proc else "never started"
            print(f"  Worker {batch.get('pid', '?')} died (exit={exit_code}), restarting...")
            if batch.get("log_fh"):
                batch["log_fh"].close()
            launch_worker(batch, model, api_base, api_key)


def prune_docker():
    """Remove stopped swe-local containers to free disk."""
    try:
        result = subprocess.run(
            ["docker", "container", "prune", "-f", "--filter", "label=swe-distill"],
            capture_output=True, text=True, timeout=30
        )
        # Also prune dangling images
        subprocess.run(
            ["docker", "image", "prune", "-f"],
            capture_output=True, text=True, timeout=30
        )
    except:
        pass


def main():
    parser = argparse.ArgumentParser(description="SWE Continuous Distillation Daemon")
    parser.add_argument("--workers", type=int, default=3, help="Number of concurrent workers")
    parser.add_argument("--poll-interval", type=int, default=1800, help="R2 poll interval in seconds (default 30min)")
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--api-base", default="https://api.aicodemirror.com/api/claudecode/v1")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--go-only", action="store_true", default=True, help="Only attempt Go+Rust tasks")
    parser.add_argument("--all-langs", action="store_true", help="Attempt all languages")
    args = parser.parse_args()

    go_only = not args.all_langs

    print("=" * 60)
    print("SWE CONTINUOUS DISTILLATION DAEMON")
    print(f"Workers: {args.workers}, Poll: {args.poll_interval}s, Go-only: {go_only}")
    print("=" * 60)

    batches = []
    last_poll = 0

    while True:
        now = time.time()

        # Poll R2 for new tasks periodically
        if now - last_poll >= args.poll_interval or not batches:
            print(f"\n[{time.strftime('%H:%M:%S')}] Polling R2 for new tasks...")

            # Kill existing workers
            for batch in batches:
                proc = batch.get("proc")
                if proc and proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=10)
                if batch.get("log_fh"):
                    batch["log_fh"].close()

            # Get current state
            attempted, success = get_attempted_ids()
            print(f"Attempted: {len(attempted)}, Successful: {len(success)}")

            # Fetch new tasks
            new_tasks = fetch_new_tasks(attempted, go_only=go_only)

            if new_tasks:
                batches = write_batch_files(new_tasks, args.workers)
                for batch in batches:
                    launch_worker(batch, args.model, args.api_base, args.api_key)
            else:
                print("No new tasks found. Will retry at next poll.")
                batches = []

            last_poll = now

            # Prune Docker
            prune_docker()

        # Check worker health every 60s
        if batches:
            check_workers(batches, args.model, args.api_base, args.api_key)

        time.sleep(60)


if __name__ == "__main__":
    main()
