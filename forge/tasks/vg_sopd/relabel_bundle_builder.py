"""Bundle builder for VG-SOPD relabel tasks."""

from __future__ import annotations

from forge.core.contracts.execution import InputRef, JobKind, JobSpec, OutputRef, ResourceRequest
from forge.core.execution.bundle import JobBundle
from forge.tasks.training.bundle_builder import _bundle_entrypoint_prelude, sanitize_job_id
from forge.tasks.vg_sopd.specs import RelabelTaskSpec


class VGRelabelBundleBuilder:
    def build(self, bundle_dir: str, *, spec: RelabelTaskSpec, resources: ResourceRequest | None = None, overwrite: bool = False) -> JobBundle:
        bundle = JobBundle.create(bundle_dir, overwrite=overwrite)
        traces_rel = bundle.copy_input(spec.frontier_traces_path)
        spec_path = "inputs/relabel_spec.json"
        spec_payload = spec.model_copy(update={"frontier_traces_path": f"${{BUNDLE_ROOT}}/{traces_rel}"}).model_dump_json(indent=2)
        bundle.write_text(spec_path, spec_payload)
        job = JobSpec(
            job_id=sanitize_job_id(f"{spec.experiment_id}-vg-relabel-{spec.iteration_index}", prefix="vg-relabel"),
            kind=JobKind.COLLECT,
            resources=resources or spec.relabel.execution.resources,
            inputs=(
                InputRef(name="frontier_traces", relative_path=traces_rel),
                InputRef(name="relabel_spec", relative_path=spec_path),
            ),
            expected_outputs=(
                OutputRef(name="relabelled_traces", relative_path="artifacts/relabelled_traces.jsonl"),
                OutputRef(name="teacher_augmented_traces", relative_path="artifacts/teacher_augmented_traces.jsonl"),
                OutputRef(name="relabel_summary", relative_path="artifacts/relabel_summary.json"),
            ),
            metadata={"task_type": "vg_relabel", "iteration_index": spec.iteration_index},
        )
        bundle.write_job(job)
        script = _bundle_entrypoint_prelude() + "\n".join(
            [
                'sed "s|\\${BUNDLE_ROOT}|${BUNDLE_ROOT}|g" "${BUNDLE_ROOT}/inputs/relabel_spec.json" > "${BUNDLE_ROOT}/runtime/relabel_spec.resolved.json"',
                '"${FORGE_PYTHON}" -m forge.tasks.vg_sopd.relabel '
                '--spec "${BUNDLE_ROOT}/runtime/relabel_spec.resolved.json" '
                '--bundle-root "${BUNDLE_ROOT}" '
                '2>&1 | tee "${BUNDLE_ROOT}/artifacts/relabel.log"',
                "",
            ]
        )
        bundle.write_text(job.entrypoint, script, executable=True)
        bundle.record_local_artifacts()
        return bundle


__all__ = ["VGRelabelBundleBuilder"]
