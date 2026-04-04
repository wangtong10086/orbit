"""Evaluation bundle builder."""

from __future__ import annotations

import shlex

from forge.core.execution.bundle import JobBundle
from forge.core.contracts.execution import JobKind, JobSpec, OutputRef, ResourceRequest
from forge.tasks.evaluation.specs import EvalTaskSpec
from forge.tasks.training.bundle_builder import _bundle_entrypoint_prelude, sanitize_job_id


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


__all__ = ["EvalBundleBuilder"]
