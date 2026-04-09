from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch multi-process model-vs-MCTS win export workers")
    parser.add_argument("--config", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--root-output-dir", required=True, help="Existing output dir to preserve and aggregate")
    parser.add_argument("--target-total-wins", type=int, default=5000)
    parser.add_argument("--worker-processes", type=int, default=8)
    parser.add_argument("--worker-num-workers", type=int, default=16)
    parser.add_argument("--worker-max-games", type=int, default=15000)
    parser.add_argument("--base-seed", type=int, default=0)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--cuda-visible-devices", default="0")
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--log-dir", default="", help="Optional log dir for worker stdout/stderr")
    return parser.parse_args()


def _count_wins(directory: Path) -> int:
    path = directory / "winning_games.jsonl"
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def _write_summary(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    args = _parse_args()
    root_output_dir = Path(args.root_output_dir)
    root_output_dir.mkdir(parents=True, exist_ok=True)
    log_dir = Path(args.log_dir) if args.log_dir else (root_output_dir / "orchestrator_logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    workers_root = root_output_dir / "workers"
    workers_root.mkdir(parents=True, exist_ok=True)

    existing_wins = _count_wins(root_output_dir)
    if existing_wins >= int(args.target_total_wins):
        _write_summary(
            root_output_dir / "orchestrator_summary.json",
            {
                "status": "completed",
                "target_total_wins": int(args.target_total_wins),
                "existing_wins": int(existing_wins),
                "total_wins": int(existing_wins),
                "message": "existing data already meets target",
            },
        )
        return

    procs: list[subprocess.Popen[str]] = []
    worker_dirs: list[Path] = []

    def _terminate_all() -> None:
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    def _signal_handler(signum, frame) -> None:
        _terminate_all()
        raise SystemExit(130)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    for index in range(int(args.worker_processes)):
        worker_dir = workers_root / f"worker_{index:02d}"
        worker_dir.mkdir(parents=True, exist_ok=True)
        worker_dirs.append(worker_dir)
        log_path = log_dir / f"worker_{index:02d}.log"
        log_handle = log_path.open("w", encoding="utf-8")
        cmd = [
            "/root/project/.venv-muzero/bin/python3",
            "-m",
            "projects.openspiel_muzero_pt.scripts.export_model_vs_mcts_wins",
            "--config",
            args.config,
            "--checkpoint",
            args.checkpoint,
            "--output-dir",
            str(worker_dir),
            "--mode",
            "quick",
            "--target-wins",
            str(max(int(args.target_total_wins), 5000)),
            "--max-games",
            str(int(args.worker_max_games)),
            "--num-workers",
            str(int(args.worker_num_workers)),
            "--seed",
            str(int(args.base_seed) + index * 100000),
            "--device",
            args.device,
        ]
        procs.append(
            subprocess.Popen(
                cmd,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                cwd="/root/project",
                env={
                    **os.environ,
                    "PYTHONPATH": "/root/project",
                    "CUDA_VISIBLE_DEVICES": str(args.cuda_visible_devices),
                },
            )
        )

    try:
        while True:
            worker_wins = {worker_dir.name: _count_wins(worker_dir) for worker_dir in worker_dirs}
            total_wins = int(existing_wins + sum(worker_wins.values()))
            _write_summary(
                root_output_dir / "orchestrator_summary.json",
                {
                    "status": "running",
                    "target_total_wins": int(args.target_total_wins),
                    "existing_wins": int(existing_wins),
                    "worker_processes": int(args.worker_processes),
                    "worker_num_workers": int(args.worker_num_workers),
                    "total_wins": int(total_wins),
                    "worker_wins": worker_wins,
                },
            )
            if total_wins >= int(args.target_total_wins):
                break
            if all(proc.poll() is not None for proc in procs):
                break
            time.sleep(float(args.poll_seconds))
    finally:
        _terminate_all()

    worker_wins = {worker_dir.name: _count_wins(worker_dir) for worker_dir in worker_dirs}
    total_wins = int(existing_wins + sum(worker_wins.values()))
    _write_summary(
        root_output_dir / "orchestrator_summary.json",
        {
            "status": "completed" if total_wins >= int(args.target_total_wins) else "stopped",
            "target_total_wins": int(args.target_total_wins),
            "existing_wins": int(existing_wins),
            "worker_processes": int(args.worker_processes),
            "worker_num_workers": int(args.worker_num_workers),
            "total_wins": int(total_wins),
            "worker_wins": worker_wins,
        },
    )


if __name__ == "__main__":
    main()
