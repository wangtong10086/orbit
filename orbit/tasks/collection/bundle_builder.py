"""Collection bundle builder."""

from __future__ import annotations

from orbit.core.execution.bundle import JobBundle
from orbit.core.contracts.execution import InputRef, JobKind, JobSpec, OutputRef, ResourceRequest
from orbit.tasks.collection.specs import CollectTaskSpec
from orbit.tasks.training.bundle_builder import _bundle_entrypoint_prelude, sanitize_job_id


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
                "\"${ORBIT_PYTHON}\" -m orbit.data.collect_publish "
                "--spec \"${BUNDLE_ROOT}/inputs/collect_spec.json\" "
                "--bundle-root \"${BUNDLE_ROOT}\" "
                "2>&1 | tee \"${BUNDLE_ROOT}/artifacts/collect.log\"",
                "",
            ]
        )
        bundle.write_text(job.entrypoint, script, executable=True)
        bundle.record_local_artifacts()
        return bundle


__all__ = ["CollectBundleBuilder"]
