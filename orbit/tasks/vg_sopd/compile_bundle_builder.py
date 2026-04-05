"""Bundle builder for VG-SOPD compiler tasks."""

from __future__ import annotations

from orbit.core.contracts.execution import InputRef, JobKind, JobSpec, OutputRef, ResourceRequest
from orbit.core.execution.bundle import JobBundle
from orbit.tasks.training.bundle_builder import _bundle_entrypoint_prelude, sanitize_job_id
from orbit.tasks.vg_sopd.specs import CompileTaskSpec


class VGCompileBundleBuilder:
    def build(self, bundle_dir: str, *, spec: CompileTaskSpec, resources: ResourceRequest | None = None, overwrite: bool = False) -> JobBundle:
        bundle = JobBundle.create(bundle_dir, overwrite=overwrite)
        relabelled_rel = bundle.copy_input(spec.relabelled_traces_path)
        teacher_rel = bundle.copy_input(spec.teacher_augmented_traces_path)
        spec_path = "inputs/compile_spec.json"
        spec_payload = spec.model_copy(
            update={
                "relabelled_traces_path": f"${{BUNDLE_ROOT}}/{relabelled_rel}",
                "teacher_augmented_traces_path": f"${{BUNDLE_ROOT}}/{teacher_rel}",
            }
        ).model_dump_json(indent=2)
        bundle.write_text(spec_path, spec_payload)
        job = JobSpec(
            job_id=sanitize_job_id(f"{spec.experiment_id}-vg-compile-{spec.iteration_index}", prefix="vg-compile"),
            kind=JobKind.COLLECT,
            resources=resources or spec.compile.execution.resources,
            inputs=(
                InputRef(name="relabelled_traces", relative_path=relabelled_rel),
                InputRef(name="teacher_augmented_traces", relative_path=teacher_rel),
                InputRef(name="compile_spec", relative_path=spec_path),
            ),
            expected_outputs=(
                OutputRef(name="compiled_sft", relative_path="artifacts/compiled_sft.jsonl"),
                OutputRef(name="compiled_preference", relative_path="artifacts/compiled_preference.jsonl"),
                OutputRef(name="compiled_gkd", relative_path="artifacts/compiled_gkd.jsonl"),
                OutputRef(name="iteration_report", relative_path="artifacts/iteration_report.json"),
            ),
            metadata={"task_type": "vg_compile", "iteration_index": spec.iteration_index},
        )
        bundle.write_job(job)
        script = _bundle_entrypoint_prelude() + "\n".join(
            [
                'sed "s|\\${BUNDLE_ROOT}|${BUNDLE_ROOT}|g" "${BUNDLE_ROOT}/inputs/compile_spec.json" > "${BUNDLE_ROOT}/runtime/compile_spec.resolved.json"',
                '"${ORBIT_PYTHON}" -m orbit.tasks.vg_sopd.compiler '
                '--spec "${BUNDLE_ROOT}/runtime/compile_spec.resolved.json" '
                '--bundle-root "${BUNDLE_ROOT}" '
                '2>&1 | tee "${BUNDLE_ROOT}/artifacts/compile.log"',
                "",
            ]
        )
        bundle.write_text(job.entrypoint, script, executable=True)
        bundle.record_local_artifacts()
        return bundle


__all__ = ["VGCompileBundleBuilder"]
