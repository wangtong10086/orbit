#!/usr/bin/env python3
"""Run bucketed ms-swift training stages inside one workspace."""

from __future__ import annotations

import argparse
import json
import shutil
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


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _merge_stage_config(base: dict, overrides: dict) -> dict:
    merged = dict(base)
    passthrough = merged.get("swift_passthrough")
    stage_passthrough = overrides.get("swift_passthrough")
    if isinstance(passthrough, dict) and isinstance(stage_passthrough, dict):
        merged["swift_passthrough"] = {**passthrough, **stage_passthrough}
        overrides = {key: value for key, value in overrides.items() if key != "swift_passthrough"}
    merged.update(overrides)
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Run staged bucketed ms-swift training from a resolved base config")
    parser.add_argument("--workspace", required=True, help="Workspace path that contains bundle/ and runtime/")
    parser.add_argument("--base-config", required=True, help="Resolved base swift YAML path")
    parser.add_argument("--plan-json", required=True, help="Bucket training plan JSON path")
    parser.add_argument("--manifest", required=True, help="Bucket manifest JSON path emitted by split script")
    parser.add_argument("--train-type", required=True, help="swift subcommand, for example sft or rlhf")
    parser.add_argument("--nproc-per-node", type=int, default=1, help="Distributed process count")
    parser.add_argument("--master-port-base", type=int, default=29650)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    workspace = Path(args.workspace)
    runtime_dir = workspace / "bundle" / "runtime"
    artifacts_dir = workspace / "bundle" / "artifacts"
    base_cfg = Path(args.base_config)
    manifest_path = Path(args.manifest)
    plan_path = Path(args.plan_json)
    if not base_cfg.exists():
        raise FileNotFoundError(base_cfg)
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)
    if not plan_path.exists():
        raise FileNotFoundError(plan_path)

    base = yaml.safe_load(base_cfg.read_text(encoding="utf-8")) or {}
    plan = _load_json(plan_path)
    manifest = _load_json(manifest_path)
    manifest_buckets = manifest.get("buckets", {})
    stage_defs = list(plan.get("stages", []))
    if not stage_defs:
        raise ValueError("bucket plan must contain at least one stage")

    initial_model = base["model"]
    initial_adapters = list(base.get("adapters", []))
    tuner_type = str(base.get("tuner_type", "")).strip().lower()
    previous_checkpoint: Path | None = None
    run_summary: list[dict[str, str | int | bool]] = []
    latest_output_root: Path | None = None

    for idx, stage in enumerate(stage_defs):
        stage_name = str(stage["name"])
        bucket_info = manifest_buckets.get(stage_name)
        if not bucket_info:
            raise KeyError(f"missing bucket manifest entry for stage {stage_name}")
        dataset_path = Path(str(bucket_info["path"]))
        if not dataset_path.exists():
            raise FileNotFoundError(dataset_path)
        if int(bucket_info.get("count", 0)) <= 0:
            run_summary.append(
                {
                    "stage": stage_name,
                    "dataset": str(dataset_path),
                    "skipped": True,
                    "reason": "empty_bucket",
                }
            )
            continue

        stage_cfg = _merge_stage_config(base, dict(stage.get("train_overrides", {})))
        if tuner_type == "lora" and previous_checkpoint is not None:
            stage_cfg["model"] = str(initial_model)
            stage_cfg["adapters"] = [str(previous_checkpoint), *initial_adapters]
        else:
            stage_cfg["model"] = str(previous_checkpoint or initial_model)
            if initial_adapters:
                stage_cfg["adapters"] = list(initial_adapters)
        stage_cfg["dataset"] = [str(dataset_path)]
        stage_cfg["max_length"] = int(stage["max_length"])
        stage_cfg["output_dir"] = f"artifacts/checkpoints-{stage_name}"

        cfg_path = runtime_dir / f"swift_config.bucket_{stage_name}.yaml"
        log_path = artifacts_dir / f"training-{stage_name}.log"
        _write_yaml(cfg_path, stage_cfg)
        run_summary.append(
            {
                "stage": stage_name,
                "dataset": str(dataset_path),
                "count": int(bucket_info.get("count", 0)),
                "config": str(cfg_path),
                "log": str(log_path),
                "model": str(stage_cfg["model"]),
                "adapters": list(stage_cfg.get("adapters", [])),
                "skipped": False,
            }
        )

        if args.dry_run:
            previous_checkpoint = Path(stage_cfg["output_dir"]) / "v*/checkpoint-*"
            continue

        shell_cmd = (
            "set -euo pipefail; "
            "if [ -f /data/.affine/activate.sh ]; then source /data/.affine/activate.sh >/dev/null 2>&1; fi; "
            f'cd "{workspace / "bundle"}"; '
            f'export NPROC_PER_NODE="{args.nproc_per_node}" MASTER_PORT="{args.master_port_base + idx}"; '
            f'"${{ORBIT_SWIFT_BIN:-swift}}" {args.train_type} --config "{cfg_path}" 2>&1 | tee "{log_path}"'
        )
        subprocess.run(["/bin/bash", "-lc", shell_cmd], check=True)
        latest_output_root = workspace / "bundle" / stage_cfg["output_dir"]
        previous_checkpoint = _latest_checkpoint(latest_output_root)

    if latest_output_root is not None:
        final_alias = artifacts_dir / "checkpoints"
        if final_alias.exists() or final_alias.is_symlink():
            if final_alias.is_dir() and not final_alias.is_symlink():
                shutil.rmtree(final_alias)
            else:
                final_alias.unlink()
        final_alias.symlink_to(latest_output_root.name)

    print(json.dumps(run_summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
