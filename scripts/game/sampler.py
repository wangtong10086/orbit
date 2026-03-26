#!/usr/bin/env python3
"""v11 自动化采集模块 — 多进程调度, 自动补充, 达标停止。

Usage:
    python3 sampler.py --cpus 120              # 本机120核
    python3 sampler.py --cpus 64 --tag work1   # 标记机器名

Features:
- 自动分配worker到未完成的游戏
- 达标的游戏自动停止, CPU转给未完成游戏
- 每60秒汇报进度
- 每个worker独立文件, 不会数据丢失
"""

import argparse
import json
import os
import sys
import time
import glob
import signal
import multiprocessing as mp
from pathlib import Path

# ============================================================
# 采集目标
# ============================================================
TARGETS = {
    "goofspiel": 2000,
    "leduc_poker": 2000,
    "liars_dice": 5000,
    "gin_rummy": 2000,
    "hex": 6500,
    "othello": 5000,
    "clobber": 10000,
}

DATADIR = "data/v11"
STOP_FLAG = mp.Event()


def count_game(game):
    """Count entries for a game across all files."""
    total = 0
    for f in glob.glob(f"{DATADIR}/v11_{game}_*.jsonl"):
        try:
            with open(f) as fh:
                total += sum(1 for _ in fh)
        except:
            pass
    return total


def worker_fn(game, worker_id, tag, batch_size):
    """Single worker: generate batch_size games, write to own file."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    os.environ.setdefault("OPENSPIEL_DIR", "/root/affinetes/environments/openspiel")

    from generate_v11 import generate_one

    seed_base = hash(f"{tag}_{worker_id}_{time.time()}") % (2**31)
    outfile = f"{DATADIR}/v11_{game}_{tag}_w{worker_id}.jsonl"

    wins = 0
    with open(outfile, "a") as f:
        for i in range(batch_size):
            if STOP_FLAG.is_set():
                break
            seed = seed_base + i
            try:
                result = generate_one(game, seed)
                if result:
                    f.write(json.dumps(result, ensure_ascii=False) + "\n")
                    f.flush()
                    wins += 1
            except Exception as e:
                pass  # Skip errors, continue

    return game, wins


def allocate_workers(total_cpus):
    """Allocate CPUs to games proportional to remaining work."""
    remaining = {}
    for game, target in TARGETS.items():
        current = count_game(game)
        left = max(0, target - current)
        if left > 0:
            remaining[game] = left

    if not remaining:
        return {}

    total_remaining = sum(remaining.values())
    allocation = {}
    allocated = 0
    games = sorted(remaining.keys(), key=lambda g: remaining[g], reverse=True)

    for game in games:
        share = max(1, int(total_cpus * remaining[game] / total_remaining))
        allocation[game] = share
        allocated += share

    # Distribute leftover CPUs to largest remaining game
    while allocated < total_cpus and games:
        allocation[games[0]] += 1
        allocated += 1

    return allocation


def run_orchestrator(total_cpus, tag, batch_size=100):
    """Main orchestrator loop."""
    os.makedirs(DATADIR, exist_ok=True)
    pool = mp.Pool(processes=total_cpus)
    active_tasks = {}  # game -> list of AsyncResult

    print(f"=== v11 Sampler: {tag} ({total_cpus} CPUs) ===")
    print(f"Targets: {TARGETS}")
    print(f"Batch size: {batch_size}")
    print()

    worker_counter = 0

    while True:
        # Check completion status
        all_done = True
        status = {}
        for game, target in TARGETS.items():
            current = count_game(game)
            status[game] = (current, target)
            if current < target:
                all_done = False

        if all_done:
            print("\n=== ALL TARGETS REACHED ===")
            for game, (cur, tgt) in status.items():
                print(f"  {game}: {cur}/{tgt}")
            break

        # Clean up finished tasks
        for game in list(active_tasks.keys()):
            active_tasks[game] = [t for t in active_tasks[game] if not t.ready()]

        # Allocate workers
        allocation = allocate_workers(total_cpus)

        # Launch new workers where needed
        for game, target_workers in allocation.items():
            current_workers = len(active_tasks.get(game, []))
            need = target_workers - current_workers
            if need > 0:
                if game not in active_tasks:
                    active_tasks[game] = []
                for _ in range(need):
                    worker_counter += 1
                    result = pool.apply_async(
                        worker_fn, (game, worker_counter, tag, batch_size)
                    )
                    active_tasks[game].append(result)

        # Status report
        total_workers = sum(len(v) for v in active_tasks.values())
        ts = time.strftime("%H:%M:%S")
        print(f"\n[{ts}] Workers: {total_workers}/{total_cpus}")
        for game in ["goofspiel", "leduc_poker", "liars_dice", "gin_rummy",
                      "hex", "othello", "clobber"]:
            cur, tgt = status[game]
            workers = len(active_tasks.get(game, []))
            pct = cur * 100 // tgt
            bar = "✓" if cur >= tgt else f"{pct}% [{workers}w]"
            print(f"  {game:<14} {cur:>6}/{tgt:<6} {bar}")

        time.sleep(60)

    pool.terminate()
    pool.join()


def main():
    parser = argparse.ArgumentParser(description="v11 automated game data sampler")
    parser.add_argument("--cpus", type=int, default=100, help="Number of CPUs to use")
    parser.add_argument("--tag", default="local", help="Machine tag for file naming")
    parser.add_argument("--batch", type=int, default=100, help="Games per worker batch")
    args = parser.parse_args()

    def signal_handler(sig, frame):
        print("\nStopping...")
        STOP_FLAG.set()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    run_orchestrator(args.cpus, args.tag, args.batch)


if __name__ == "__main__":
    main()
