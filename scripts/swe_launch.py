#!/usr/bin/env python3
"""
SWE Distillation Launcher — Systematic concurrent distillation.

Usage:
    python3 swe_launch.py --task-file <file> --workers 3 --model claude-sonnet-4-6 --api-base <url> --api-key <key>

Features:
- Splits task file into N chunks for concurrent processing
- Each worker gets its own output file and log file
- Resume-safe (--resume skips completed instance_ids)
- Tracks all worker PIDs in a manifest file
- Can be re-run safely — only processes uncovered tasks
"""
import argparse
import json
import os
import subprocess
import sys
import time

def split_tasks(task_file: str, n_workers: int) -> list[str]:
    """Split task file into N chunk files."""
    tasks = [json.loads(line) for line in open(task_file)]
    if not tasks:
        print(f"ERROR: {task_file} is empty")
        sys.exit(1)

    chunk_size = (len(tasks) + n_workers - 1) // n_workers
    chunk_files = []
    base = os.path.splitext(os.path.basename(task_file))[0]

    for i in range(n_workers):
        chunk = tasks[i * chunk_size : (i + 1) * chunk_size]
        if not chunk:
            break
        fname = f"/root/{base}_w{i}.jsonl"
        with open(fname, "w") as f:
            for t in chunk:
                f.write(json.dumps(t) + "\n")
        chunk_files.append(fname)
        print(f"  Worker {i}: {fname} ({len(chunk)} tasks)")

    return chunk_files


def launch_workers(chunk_files: list[str], model: str, api_base: str, api_key: str) -> list[dict]:
    """Launch a distill process for each chunk."""
    workers = []
    for i, chunk_file in enumerate(chunk_files):
        base = os.path.splitext(os.path.basename(chunk_file))[0]
        output_file = f"/root/real_distill_{base}.jsonl"
        log_file = f"/root/swe_distill_{base}.log"

        cmd = (
            f"cd /root && nohup python3 -u swe_distill.py "
            f"--task-file {chunk_file} "
            f"--output {output_file} "
            f"--resume --local-only "
            f"--model {model} "
            f"--api-base {api_base} "
            f"--api-key {api_key} "
            f"> {log_file} 2>&1 &"
        )
        os.system(cmd)
        time.sleep(1)

        # Get PID
        result = subprocess.run(
            ["pgrep", "-f", f"--task-file {chunk_file}"],
            capture_output=True, text=True
        )
        pid = result.stdout.strip().split("\n")[0] if result.stdout.strip() else "unknown"

        workers.append({
            "worker_id": i,
            "pid": pid,
            "task_file": chunk_file,
            "output_file": output_file,
            "log_file": log_file,
            "model": model,
        })
        print(f"  Worker {i}: PID {pid}, output={output_file}")

    return workers


def main():
    parser = argparse.ArgumentParser(description="SWE Distillation Launcher")
    parser.add_argument("--task-file", required=True, help="JSONL file with tasks")
    parser.add_argument("--workers", type=int, default=3, help="Number of concurrent workers")
    parser.add_argument("--model", default="claude-sonnet-4-6", help="Model name")
    parser.add_argument("--api-base", required=True, help="API base URL")
    parser.add_argument("--api-key", required=True, help="API key")
    args = parser.parse_args()

    print("=" * 60)
    print(f"SWE DISTILLATION LAUNCHER")
    print(f"  Task file: {args.task_file}")
    print(f"  Workers: {args.workers}")
    print(f"  Model: {args.model}")
    print(f"  API base: {args.api_base[:50]}...")
    print("=" * 60)

    # Count tasks
    n_tasks = sum(1 for _ in open(args.task_file))
    print(f"\nTotal tasks: {n_tasks}")
    print(f"Workers: {args.workers}")
    print(f"Tasks per worker: ~{(n_tasks + args.workers - 1) // args.workers}")

    # Split
    print(f"\nSplitting tasks...")
    chunk_files = split_tasks(args.task_file, args.workers)

    # Launch
    print(f"\nLaunching {len(chunk_files)} workers...")
    workers = launch_workers(chunk_files, args.model, args.api_base, args.api_key)

    # Save manifest
    manifest = {
        "task_file": args.task_file,
        "n_tasks": n_tasks,
        "n_workers": len(workers),
        "model": args.model,
        "api_base": args.api_base,
        "workers": workers,
        "launched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    manifest_file = "/root/swe_launch_manifest.json"
    with open(manifest_file, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nManifest saved: {manifest_file}")
    print(f"Monitor: watch -n5 'wc -l /root/real_distill_*_w*.jsonl 2>/dev/null'")
    print(f"\nAll {len(workers)} workers launched successfully.")


if __name__ == "__main__":
    main()
