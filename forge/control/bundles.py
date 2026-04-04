"""Task-layer bundle builders."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from forge.control.task_specs import CollectTaskSpec, EvalTaskSpec
from forge.execution.bundle import JobBundle
from forge.execution.contracts import InputRef, JobKind, JobSpec, OutputRef, ResourceRequest
from forge.foundation.contracts import TrainingSpec
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
    if [ -z "${FORGE_PYTHON:-}" ]; then
        export FORGE_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
        export PATH="${PROJECT_ROOT}/.venv/bin:${PATH}"
    fi
else
    export FORGE_PYTHON="${FORGE_PYTHON:-python3}"
fi
if [ "${FORGE_SKIP_DOTENV:-0}" != "1" ] && [ -f "${PROJECT_ROOT}/.env" ]; then
    set -a
    . "${PROJECT_ROOT}/.env"
    set +a
fi
PARENT_ROOT="$(cd "${PROJECT_ROOT}/.." && pwd)"
if [ -d "${PARENT_ROOT}/affinetes" ]; then
    export PYTHONPATH="${PROJECT_ROOT}:${PARENT_ROOT}:${PYTHONPATH:-}"
else
    export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"
fi
cd "${PROJECT_ROOT}"
"""


class TrainBundleBuilder:
    def __init__(self, backend: SwiftBackend | None = None):
        self.backend = backend or SwiftBackend()

    def build(self, bundle_dir: str, *, spec: TrainingSpec, resources: ResourceRequest | None = None, overwrite: bool = False) -> JobBundle:
        issues = self.backend.validate_config(spec.train_config)
        if issues:
            raise ValueError(f"Invalid SwiftConfig: {issues}")
        bundle = JobBundle.create(bundle_dir, overwrite=overwrite)
        dataset_rel = bundle.copy_input(spec.dataset_path)
        cfg = SwiftConfig.model_validate(spec.train_config.model_dump())
        cfg.output_dir = "artifacts/checkpoints"
        yaml_path = "inputs/swift_config.yaml"
        bundle.write_text(yaml_path, cfg.to_yaml(dataset_rel))
        job = JobSpec(
            job_id=sanitize_job_id(spec.experiment_id, prefix="train"),
            kind=JobKind.TRAIN,
            resources=resources or ResourceRequest(),
            inputs=(InputRef(name="dataset", relative_path=dataset_rel), InputRef(name="swift_config", relative_path=yaml_path)),
            expected_outputs=(
                OutputRef(name="training_log", relative_path="artifacts/training.log"),
                OutputRef(name="checkpoints", relative_path="artifacts/checkpoints", kind="dir"),
            ),
            metadata={
                "task_type": "train",
                "model": cfg.model,
                "dataset_filename": Path(dataset_rel).name,
                "train_type": cfg.train_type,
            },
        )
        bundle.write_job(job)
        swift_cmd = cfg.swift_command_from_yaml('"${BUNDLE_ROOT}/inputs/swift_config.yaml"')
        script = _bundle_entrypoint_prelude() + "\n".join(
            [
                'if [ -f /data/.affine/activate.sh ]; then source /data/.affine/activate.sh >/dev/null 2>&1; fi',
                f"{swift_cmd} 2>&1 | tee \"${{BUNDLE_ROOT}}/artifacts/training.log\"",
                "",
            ]
        )
        bundle.write_text(job.entrypoint, script, executable=True)
        bundle.record_local_artifacts()
        return bundle


class EvalBundleBuilder:
    def build(self, bundle_dir: str, *, job_id: str, spec: EvalTaskSpec, resources: ResourceRequest | None = None, overwrite: bool = False) -> JobBundle:
        bundle = JobBundle.create(bundle_dir, overwrite=overwrite)
        job = JobSpec(
            job_id=sanitize_job_id(job_id, prefix="eval"),
            kind=JobKind.EVAL,
            resources=resources or ResourceRequest(),
            expected_outputs=(
                OutputRef(name="eval_dir", relative_path=f"artifacts/{spec.output_subdir}", kind="dir"),
                OutputRef(name="eval_summary", relative_path=f"artifacts/{spec.output_subdir}/eval_summary.json"),
            ),
            metadata={
                "task_type": "eval",
                "model": spec.model,
                "environments": list(spec.environments),
                "samples": spec.samples,
            },
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
        bundle.write_text(job.entrypoint, script, executable=True)
        bundle.record_local_artifacts()
        return bundle


class CollectBundleBuilder:
    def build(self, bundle_dir: str, *, job_id: str, spec: CollectTaskSpec, resources: ResourceRequest | None = None, overwrite: bool = False) -> JobBundle:
        bundle = JobBundle.create(bundle_dir, overwrite=overwrite)
        spec_path = "inputs/collect_spec.json"
        bundle.write_text(spec_path, spec.model_dump_json(indent=2))
        job = JobSpec(
            job_id=sanitize_job_id(job_id, prefix="collect"),
            kind=JobKind.COLLECT,
            resources=resources or ResourceRequest(),
            inputs=(InputRef(name="collect_spec", relative_path=spec_path),),
            expected_outputs=(
                OutputRef(name="collect_output", relative_path=f"artifacts/staging/{spec.output_filename}"),
                OutputRef(name="publish_result", relative_path="artifacts/publish_result.json"),
                OutputRef(name="canonical_dir", relative_path="artifacts/canonical", kind="dir"),
                OutputRef(name="mixed_dir", relative_path="artifacts/mixed", kind="dir"),
                OutputRef(name="raw_dir", relative_path=f"artifacts/raw/{spec.env.lower().replace('-', '_')}", kind="dir"),
            ),
            metadata={
                "task_type": "collect",
                "env": spec.env,
                "collector": spec.collector,
                "output_filename": spec.output_filename,
            },
        )
        bundle.write_job(job)
        script = _bundle_entrypoint_prelude() + "\n".join(
            [
                "if [ -f /data/.affine/activate.sh ]; then source /data/.affine/activate.sh >/dev/null 2>&1; fi",
                "\"${FORGE_PYTHON}\" -m forge.data.collect_publish "
                "--spec \"${BUNDLE_ROOT}/inputs/collect_spec.json\" "
                "--bundle-root \"${BUNDLE_ROOT}\" "
                "2>&1 | tee \"${BUNDLE_ROOT}/artifacts/collect.log\"",
                "",
            ]
        )
        bundle.write_text(job.entrypoint, script, executable=True)
        bundle.record_local_artifacts()
        return bundle
