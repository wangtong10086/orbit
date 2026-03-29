"""Task renderers for the execution plane."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

from forge.execution.bundle import JobBundle
from forge.execution.contracts import (
    CollectTaskSpec,
    EvalTaskSpec,
    InputRef,
    JobKind,
    JobSpec,
    NavworldCollectConfig,
    OutputRef,
    ResourceRequest,
    RuntimePreferences,
    TrainTaskSpec,
)
from forge.training.config import SwiftConfig
from forge.training.sft import SwiftBackend


def sanitize_job_id(raw: str, prefix: str = "job") -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", raw).strip("-_.")
    return slug or prefix


def _bundle_entrypoint_prelude() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail
BUNDLE_ROOT="${BUNDLE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${BUNDLE_ROOT}/.." && pwd)}"
mkdir -p "${BUNDLE_ROOT}/artifacts" "${BUNDLE_ROOT}/runtime"
if [ -x "${PROJECT_ROOT}/.venv/bin/python" ]; then
    export FORGE_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
    export PATH="${PROJECT_ROOT}/.venv/bin:${PATH}"
else
    export FORGE_PYTHON="${FORGE_PYTHON:-python3}"
fi
if [ -f "${PROJECT_ROOT}/.env" ]; then
    set -a
    . "${PROJECT_ROOT}/.env"
    set +a
fi
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"
cd "${PROJECT_ROOT}"
"""


class TrainTaskRenderer:
    """Render ms-swift training tasks into standalone bundles."""

    def __init__(self, backend: SwiftBackend | None = None):
        self.backend = backend or SwiftBackend()

    def render(
        self,
        bundle_dir: str,
        *,
        job_id: str,
        dataset_path: str,
        config: SwiftConfig,
        resources: ResourceRequest | None = None,
        runtime_preferences: RuntimePreferences | None = None,
        overwrite: bool = False,
    ) -> JobBundle:
        issues = self.backend.validate_config(config)
        if issues:
            raise ValueError(f"Invalid SwiftConfig: {issues}")

        bundle = JobBundle.create(bundle_dir, overwrite=overwrite)
        dataset_rel = bundle.copy_input(dataset_path)
        cfg = SwiftConfig.model_validate(config.model_dump())
        cfg.output_dir = "artifacts/checkpoints"
        yaml_path = "inputs/swift_config.yaml"
        bundle.write_text(yaml_path, cfg.to_yaml(dataset_rel))

        job = JobSpec(
            job_id=sanitize_job_id(job_id, prefix="train"),
            kind=JobKind.TRAIN,
            resources=resources or ResourceRequest(),
            runtime_preferences=runtime_preferences or RuntimePreferences(),
            inputs=(InputRef(name="dataset", relative_path=dataset_rel), InputRef(name="swift_config", relative_path=yaml_path)),
            expected_outputs=(
                OutputRef(name="training_log", relative_path="artifacts/training.log"),
                OutputRef(name="checkpoints", relative_path="artifacts/checkpoints", kind="dir"),
            ),
            task=TrainTaskSpec(
                model=cfg.model,
                dataset_filename=Path(dataset_rel).name,
                train_config=cfg,
                train_type=cfg.train_type,
            ),
        )
        bundle.write_job(job)

        swift_cmd = cfg.swift_command_from_yaml("inputs/swift_config.yaml")
        script = _bundle_entrypoint_prelude() + "\n".join(
            [
                'if [ -f /data/.affine/activate.sh ]; then source /data/.affine/activate.sh >/dev/null 2>&1; fi',
                f"{swift_cmd} 2>&1 | tee \"${{BUNDLE_ROOT}}/artifacts/training.log\"",
                "",
            ]
        )
        bundle.write_text("scripts/entrypoint.sh", script, executable=True)
        bundle.record_local_artifacts()
        return bundle


class EvalTaskRenderer:
    """Render evaluation tasks into bundles."""

    def render(
        self,
        bundle_dir: str,
        *,
        job_id: str,
        spec: EvalTaskSpec,
        resources: ResourceRequest | None = None,
        runtime_preferences: RuntimePreferences | None = None,
        overwrite: bool = False,
    ) -> JobBundle:
        bundle = JobBundle.create(bundle_dir, overwrite=overwrite)
        job = JobSpec(
            job_id=sanitize_job_id(job_id, prefix="eval"),
            kind=JobKind.EVAL,
            resources=resources or ResourceRequest(),
            runtime_preferences=runtime_preferences or RuntimePreferences(),
            expected_outputs=(
                OutputRef(name="eval_dir", relative_path=f"artifacts/{spec.output_subdir}", kind="dir"),
                OutputRef(name="eval_summary", relative_path=f"artifacts/{spec.output_subdir}/eval_summary.json"),
            ),
            task=spec,
        )
        bundle.write_job(job)

        envs = " ".join(shlex.quote(env) for env in spec.environments)
        script = _bundle_entrypoint_prelude() + "\n".join(
            [
                "if [ -f /data/.affine/activate.sh ]; then source /data/.affine/activate.sh >/dev/null 2>&1; fi",
                f"\"${{FORGE_PYTHON}}\" \"${{PROJECT_ROOT}}/scripts/eval_envs.py\" "
                f"--base-url {shlex.quote(spec.base_url)} "
                f"--model {shlex.quote(spec.model)} "
                f"--samples {spec.samples} "
                f"--concurrency {spec.concurrency} "
                f"--seed {spec.seed} "
                f"--output-dir \"${{BUNDLE_ROOT}}/artifacts/{spec.output_subdir}\" "
                f"--affinetes-dir {shlex.quote(spec.affinetes_dir)} "
                f"--envs {envs}"
                + (" --skip-build" if spec.skip_build else "")
                + (f" --api-key {shlex.quote(spec.api_key)}" if spec.api_key else "")
                + " 2>&1 | tee \"${BUNDLE_ROOT}/artifacts/eval.log\"",
                "",
            ]
        )
        bundle.write_text("scripts/entrypoint.sh", script, executable=True)
        bundle.record_local_artifacts()
        return bundle


class CollectTaskRenderer:
    """Render data-collection tasks into bundles."""

    def render_navworld(
        self,
        bundle_dir: str,
        *,
        job_id: str,
        spec: CollectTaskSpec,
        resources: ResourceRequest | None = None,
        runtime_preferences: RuntimePreferences | None = None,
        overwrite: bool = False,
    ) -> JobBundle:
        if spec.collector != "navworld-gen":
            raise ValueError(f"Unsupported collector: {spec.collector}")

        bundle = JobBundle.create(bundle_dir, overwrite=overwrite)
        job = JobSpec(
            job_id=sanitize_job_id(job_id, prefix="collect"),
            kind=JobKind.COLLECT,
            resources=resources or ResourceRequest(),
            runtime_preferences=runtime_preferences or RuntimePreferences(),
            expected_outputs=(OutputRef(name="collect_output", relative_path=f"artifacts/{spec.output_filename}"),),
            task=spec,
        )
        bundle.write_job(job)

        config = spec.config if isinstance(spec.config, NavworldCollectConfig) else NavworldCollectConfig.model_validate(spec.config)
        num = config.num
        model = config.model
        start_id = config.start_id
        concurrency = config.concurrency
        problem_type = config.problem_type
        phase1 = config.phase1
        output_name = spec.output_filename
        python_block = f"""\"${{FORGE_PYTHON}}\" - <<'PY'
import asyncio
import os
from forge.data.navworld_gen import generate_batch
from forge.data.navworld_prompts import PHASE1_TYPES

amap_key = os.environ.get("AMAP_API_KEY") or os.environ.get("AMAP_MAPS_API_KEY", "")
api_key = os.environ.get("QWEN_API_KEY") or os.environ.get("CHUTES_API_KEY", "")
if not amap_key:
    raise SystemExit("AMAP_API_KEY or AMAP_MAPS_API_KEY not set")
if not api_key:
    raise SystemExit("QWEN_API_KEY or CHUTES_API_KEY not set")

async def _main():
    output_path = os.path.join(os.environ["BUNDLE_ROOT"], "artifacts", {output_name!r})
    if {phase1!r}:
        total = 0
        for ptype in PHASE1_TYPES:
            out = output_path.replace(".jsonl", f"_{{ptype}}.jsonl")
            await generate_batch(
                num_samples={num},
                output_path=out,
                amap_key=amap_key,
                api_key=api_key,
                model={model!r},
                start_id={start_id} + total,
                concurrency={concurrency},
                problem_type=ptype,
            )
            total += {num}
    else:
        await generate_batch(
            num_samples={num},
            output_path=output_path,
            amap_key=amap_key,
            api_key=api_key,
            model={model!r},
            start_id={start_id},
            concurrency={concurrency},
            problem_type={problem_type!r},
        )

asyncio.run(_main())
PY"""
        script = _bundle_entrypoint_prelude() + "\n".join(
            [
                "if [ -f /data/.affine/activate.sh ]; then source /data/.affine/activate.sh >/dev/null 2>&1; fi",
                "{",
                python_block,
                "} 2>&1 | tee \"${BUNDLE_ROOT}/artifacts/collect.log\"",
                "",
            ]
        )
        bundle.write_text("scripts/entrypoint.sh", script, executable=True)
        bundle.record_local_artifacts()
        return bundle
