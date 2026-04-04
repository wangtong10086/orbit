"""Evaluation task plugin."""

from __future__ import annotations

from forge.core.contracts.execution import ArtifactManifest, JobKind, RunStatus
from forge.core.contracts.results import TaskSummary
from forge.core.contracts.tasks import TaskSubmission
from forge.core.execution.bundle import JobBundle
from forge.tasks.evaluation.bundle_builder import EvalBundleBuilder
from forge.tasks.evaluation.result_summary import summarize_evaluation_result
from forge.tasks.evaluation.specs import EvalTaskSpec


class EvaluationPlugin:
    task_type = "evaluation"
    job_kind = JobKind.EVAL

    def __init__(self, builder: EvalBundleBuilder | None = None):
        self.builder = builder or EvalBundleBuilder()

    def parse_request(self, raw: dict | EvalTaskSpec) -> EvalTaskSpec:
        return raw if isinstance(raw, EvalTaskSpec) else EvalTaskSpec.model_validate(raw)

    def validate_request(self, request: EvalTaskSpec) -> list[str]:
        issues: list[str] = []
        if not request.model:
            issues.append("model is required")
        if not request.environments:
            issues.append("environments is required")
        return issues

    def build_bundle(self, *, bundle_dir: str, submission: TaskSubmission) -> JobBundle:
        request = self.parse_request(submission.task_request)
        issues = self.validate_request(request)
        if issues:
            raise ValueError(f"Evaluation request validation failed: {issues}")
        return self.builder.build(bundle_dir, job_id=f"{submission.experiment_id}-eval", spec=request, overwrite=True)

    def summarize_result(
        self,
        *,
        submission: TaskSubmission,
        bundle: JobBundle,
        status: RunStatus | None,
        manifest: ArtifactManifest | None,
    ) -> TaskSummary:
        return summarize_evaluation_result(bundle=bundle, status=status, manifest=manifest)
