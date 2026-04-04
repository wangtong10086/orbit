"""Collection task plugin."""

from __future__ import annotations

from forge.core.contracts.execution import ArtifactManifest, JobKind, RunStatus
from forge.core.contracts.results import TaskSummary
from forge.core.contracts.tasks import TaskSubmission
from forge.core.execution.bundle import JobBundle
from forge.tasks.collection.bundle_builder import CollectBundleBuilder
from forge.tasks.collection.result_summary import summarize_collection_result
from forge.tasks.collection.specs import CollectTaskSpec


class CollectionPlugin:
    task_type = "collection"
    job_kind = JobKind.COLLECT

    def __init__(self, builder: CollectBundleBuilder | None = None):
        self.builder = builder or CollectBundleBuilder()

    def parse_request(self, raw: dict | CollectTaskSpec) -> CollectTaskSpec:
        return raw if isinstance(raw, CollectTaskSpec) else CollectTaskSpec.model_validate(raw)

    def validate_request(self, request: CollectTaskSpec) -> list[str]:
        issues: list[str] = []
        if not request.output_filename:
            issues.append("output_filename is required")
        return issues

    def build_bundle(self, *, bundle_dir: str, submission: TaskSubmission) -> JobBundle:
        request = self.parse_request(submission.task_request)
        issues = self.validate_request(request)
        if issues:
            raise ValueError(f"Collection request validation failed: {issues}")
        return self.builder.build(bundle_dir, job_id=f"{submission.experiment_id}-collect", spec=request, overwrite=True)

    def summarize_result(
        self,
        *,
        submission: TaskSubmission,
        bundle: JobBundle,
        status: RunStatus | None,
        manifest: ArtifactManifest | None,
    ) -> TaskSummary:
        return summarize_collection_result(bundle=bundle, status=status, manifest=manifest)
