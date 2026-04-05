"""Bundle builder for VG-SOPD frontier tasks."""

from __future__ import annotations

from forge.core.contracts.execution import InputRef, JobKind, JobSpec, OutputRef, ResourceRequest
from forge.core.execution.bundle import JobBundle
from forge.tasks.training.bundle_builder import _bundle_entrypoint_prelude, sanitize_job_id
from forge.tasks.vg_sopd.specs import FrontierTaskSpec


class VGFrontierBundleBuilder:
    def build(self, bundle_dir: str, *, spec: FrontierTaskSpec, resources: ResourceRequest | None = None, overwrite: bool = False) -> JobBundle:
        bundle = JobBundle.create(bundle_dir, overwrite=overwrite)
        task_source_rel = bundle.copy_input(spec.task_source_path)
        spec_path = "inputs/frontier_spec.json"
        spec_payload = spec.model_copy(update={"task_source_path": f"${{BUNDLE_ROOT}}/{task_source_rel}"}).model_dump_json(indent=2)
        bundle.write_text(spec_path, spec_payload)
        job = JobSpec(
            job_id=sanitize_job_id(f"{spec.experiment_id}-vg-frontier-{spec.iteration_index}", prefix="vg-frontier"),
            kind=JobKind.COLLECT,
            resources=resources or spec.rollout.execution.resources,
            inputs=(
                InputRef(name="task_source", relative_path=task_source_rel),
                InputRef(name="frontier_spec", relative_path=spec_path),
            ),
            expected_outputs=(
                OutputRef(name="raw_rollouts", relative_path="artifacts/raw_rollouts.jsonl"),
                OutputRef(name="frontier_summary", relative_path="artifacts/frontier_summary.json"),
            ),
            metadata={"task_type": "vg_frontier", "iteration_index": spec.iteration_index},
        )
        bundle.write_job(job)
        script = _bundle_entrypoint_prelude() + "\n".join(
            [
                'sed "s|\\${BUNDLE_ROOT}|${BUNDLE_ROOT}|g" "${BUNDLE_ROOT}/inputs/frontier_spec.json" > "${BUNDLE_ROOT}/runtime/frontier_spec.resolved.json"',
                '"${FORGE_PYTHON}" -m forge.tasks.vg_sopd.frontier '
                '--spec "${BUNDLE_ROOT}/runtime/frontier_spec.resolved.json" '
                '--bundle-root "${BUNDLE_ROOT}" '
                '2>&1 | tee "${BUNDLE_ROOT}/artifacts/frontier.log"',
                "",
            ]
        )
        bundle.write_text(job.entrypoint, script, executable=True)
        bundle.record_local_artifacts()
        return bundle


__all__ = ["VGFrontierBundleBuilder"]
