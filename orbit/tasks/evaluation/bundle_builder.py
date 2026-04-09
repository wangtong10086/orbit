"""Evaluation bundle builder."""

from __future__ import annotations

from pathlib import Path
import shlex
import shutil

from orbit.core.execution.bundle import JobBundle
from orbit.core.contracts.execution import InputRef, JobKind, JobSpec, OutputRef, ResourceRequest
from orbit.tasks.evaluation.specs import EvalTaskSpec
from orbit.tasks.training.bundle_builder import _bundle_entrypoint_prelude, sanitize_job_id


class EvalBundleBuilder:
    def build(self, bundle_dir: str, *, job_id: str, spec: EvalTaskSpec, resources: ResourceRequest | None = None, overwrite: bool = False) -> JobBundle:
        bundle = JobBundle.create(bundle_dir, overwrite=overwrite)
        inputs: list[InputRef] = []
        model_ref = spec.model
        task_source_ref = spec.task_source_path

        def _stage_local_path(raw: str, *, prefix: str) -> tuple[str, str]:
            source = Path(str(raw)).expanduser()
            if not source.exists():
                return "", raw
            target_name = f"{prefix}-{source.name}"
            target_path = bundle.inputs_dir / target_name
            if source.is_dir():
                shutil.copytree(source, target_path)
            else:
                shutil.copy2(source, target_path)
            return str(target_path.relative_to(bundle.path)), "__ORBIT_LOCAL_PATH__"

        model_rel, model_ref = _stage_local_path(spec.model, prefix="model")
        if model_rel:
            inputs.append(InputRef(name="model", relative_path=model_rel))
        task_rel, task_source_ref = _stage_local_path(spec.task_source_path, prefix="task-source") if spec.task_source_path else ("", spec.task_source_path)
        if task_rel:
            inputs.append(InputRef(name="task_source", relative_path=task_rel))
        job = JobSpec(
            job_id=sanitize_job_id(job_id, prefix="eval"),
            kind=JobKind.EVAL,
            resources=resources or ResourceRequest(),
            inputs=tuple(inputs),
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
        if spec.task_source_path:
            script_lines = [
                f'EVAL_MODEL={shlex.quote(model_ref)}',
                *([f'EVAL_TASK_SOURCE={shlex.quote(task_source_ref)}'] if spec.task_source_path else []),
                *([f'EVAL_MODEL="${{BUNDLE_ROOT}}/{model_rel}"', ''] if model_rel else []),
                *([f'EVAL_TASK_SOURCE="${{BUNDLE_ROOT}}/{task_rel}"', ''] if task_rel else []),
                f"\"${{ORBIT_PYTHON}}\" -m orbit.tasks.evaluation.task_source_eval "
                f"--model \"$EVAL_MODEL\" "
                f"--task-source \"$EVAL_TASK_SOURCE\" "
                f"--output-dir \"${{BUNDLE_ROOT}}/artifacts/{spec.output_subdir}\" "
                f"--seed {spec.seed} "
                f"--max-new-tokens {spec.max_new_tokens} "
                f"--temperature {spec.temperature} "
                + " 2>&1 | tee \"${BUNDLE_ROOT}/artifacts/eval.log\"",
                "",
            ]
        else:
            script_lines = [
                "if [ -f /data/.affine/activate.sh ]; then source /data/.affine/activate.sh >/dev/null 2>&1; fi",
                f"\"${{ORBIT_PYTHON}}\" \"${{PROJECT_ROOT}}/scripts/eval_envs.py\" "
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
        script = _bundle_entrypoint_prelude() + "\n".join(script_lines)
        bundle.write_text(job.entrypoint, script, executable=True)
        bundle.record_local_artifacts()
        return bundle


__all__ = ["EvalBundleBuilder"]
