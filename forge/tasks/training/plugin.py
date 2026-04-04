"""Training task plugin."""

from __future__ import annotations

from forge.core.contracts.execution import ArtifactManifest, JobKind, RunStatus
from forge.core.contracts.results import TaskSummary
from forge.core.contracts.tasks import TaskSubmission
from forge.core.execution.bundle import JobBundle
from forge.foundation.contracts import TrainingSpec
from forge.tasks.training.bundle_builder import TrainBundleBuilder
from forge.tasks.training.result_summary import summarize_training_result


class TrainingPlugin:
    task_type = "training"
    job_kind = JobKind.TRAIN

    def __init__(self, builder: TrainBundleBuilder | None = None):
        self.builder = builder or TrainBundleBuilder()

    def parse_request(self, raw: dict | TrainingSpec) -> TrainingSpec:
        return raw if isinstance(raw, TrainingSpec) else TrainingSpec.model_validate(raw)

    def validate_request(self, request: TrainingSpec) -> list[str]:
        issues: list[str] = []
        if not request.dataset_path:
            issues.append("dataset_path is required")
        if not request.output_dir:
            issues.append("output_dir is required")
        return issues

    def build_bundle(self, *, bundle_dir: str, submission: TaskSubmission) -> JobBundle:
        request = self.parse_request(submission.task_request)
        issues = self.validate_request(request)
        if issues:
            raise ValueError(f"Training request validation failed: {issues}")
        return self.builder.build(bundle_dir, spec=request, overwrite=True)

    def summarize_result(
        self,
        *,
        submission: TaskSubmission,
        bundle: JobBundle,
        status: RunStatus | None,
        manifest: ArtifactManifest | None,
    ) -> TaskSummary:
        return summarize_training_result(bundle=bundle, status=status, manifest=manifest)
