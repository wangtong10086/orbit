#!/usr/bin/env python3
"""Run bucketed native ms-swift GKD stages inside an existing workspace."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import yaml


def _latest_checkpoint(root: Path) -> Path:
    candidates = sorted(root.glob("v*/checkpoint-*"))
    if not candidates:
        raise FileNotFoundError(f"no checkpoints found under {root}")
    return candidates[-1]


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 8k/16k/32k bucketed GKD hot-update stages in one workspace")
    parser.add_argument("--workspace", required=True, help="Remote workspace path")
    parser.add_argument("--nproc-per-node", type=int, default=8, help="torch.distributed process count")
    parser.add_argument("--batch-size-8k", type=int, default=1)
    parser.add_argument("--batch-size-16k", type=int, default=1)
    parser.add_argument("--batch-size-32k", type=int, default=1)
    parser.add_argument("--grad-accum-8k", type=int, default=1)
    parser.add_argument("--grad-accum-16k", type=int, default=1)
    parser.add_argument("--grad-accum-32k", type=int, default=1)
    parser.add_argument("--dataset-num-proc-8k", type=int, default=4)
    parser.add_argument("--dataset-num-proc-16k", type=int, default=2)
    parser.add_argument("--dataset-num-proc-32k", type=int, default=1)
    parser.add_argument("--logging-steps", type=int, default=1)
    parser.add_argument("--save-steps", type=int, default=50)
    parser.add_argument("--master-port-base", type=int, default=29650)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    workspace = Path(args.workspace)
    runtime_dir = workspace / "bundle" / "runtime"
    base_cfg = runtime_dir / "swift_config.resolved.yaml"
    if not base_cfg.exists():
        raise FileNotFoundError(base_cfg)

    with base_cfg.open(encoding="utf-8") as handle:
        base = yaml.safe_load(handle) or {}

    bucket_dir = workspace / "bucketed"
    stage_defs = [
        {
            "name": "b8",
            "dataset": bucket_dir / "le_8192.jsonl",
            "max_length": 8192,
            "batch_size": args.batch_size_8k,
            "grad_accum": args.grad_accum_8k,
            "dataset_num_proc": args.dataset_num_proc_8k,
        },
        {
            "name": "b16",
            "dataset": bucket_dir / "8193_16384.jsonl",
            "max_length": 16384,
            "batch_size": args.batch_size_16k,
            "grad_accum": args.grad_accum_16k,
            "dataset_num_proc": args.dataset_num_proc_16k,
        },
        {
            "name": "b32",
            "dataset": bucket_dir / "gt_16384.jsonl",
            "max_length": 32768,
            "batch_size": args.batch_size_32k,
            "grad_accum": args.grad_accum_32k,
            "dataset_num_proc": args.dataset_num_proc_32k,
        },
    ]

    previous_model = base["model"]
    plan: list[dict[str, str]] = []

    for idx, stage in enumerate(stage_defs):
        if not stage["dataset"].exists():
            raise FileNotFoundError(stage["dataset"])
        stage_cfg = dict(base)
        stage_cfg["model"] = str(previous_model)
        stage_cfg["dataset"] = [str(stage["dataset"])]
        stage_cfg["max_length"] = stage["max_length"]
        stage_cfg["per_device_train_batch_size"] = stage["batch_size"]
        stage_cfg["gradient_accumulation_steps"] = stage["grad_accum"]
        stage_cfg["dataset_num_proc"] = stage["dataset_num_proc"]
        stage_cfg["logging_steps"] = args.logging_steps
        stage_cfg["save_steps"] = args.save_steps
        stage_cfg["output_dir"] = f"artifacts/checkpoints-{stage['name']}"

        cfg_path = runtime_dir / f"swift_config.bucket_{stage['name']}.yaml"
        log_path = workspace / "bundle" / "artifacts" / f"training-{stage['name']}.log"
        _write_yaml(cfg_path, stage_cfg)
        plan.append(
            {
                "stage": stage["name"],
                "config": str(cfg_path),
                "log": str(log_path),
                "output_dir": stage_cfg["output_dir"],
                "model": str(previous_model),
                "dataset": str(stage["dataset"]),
            }
        )

        if not args.dry_run:
            shell_cmd = (
                "set -euo pipefail; "
                "if [ -f /data/.affine/activate.sh ]; then source /data/.affine/activate.sh >/dev/null 2>&1; fi; "
                f'cd "{workspace / "bundle"}"; '
                f'export NPROC_PER_NODE="{args.nproc_per_node}" MASTER_PORT="{args.master_port_base + idx}"; '
                f'/opt/orbit-venv/bin/swift rlhf --config "{cfg_path}" 2>&1 | tee "{log_path}"'
            )
            subprocess.run(
                ["/bin/bash", "-lc", shell_cmd],
                check=True,
            )
            previous_model = _latest_checkpoint(workspace / "bundle" / stage_cfg["output_dir"])
        else:
            previous_model = Path(stage_cfg["output_dir"]) / "v*/checkpoint-*"

    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
