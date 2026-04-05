"""Task plugin for the VG-SOPD frontier stage."""

from __future__ import annotations

from forge.core.contracts.execution import ArtifactManifest, JobKind, RunStatus
from forge.core.contracts.results import TaskSummary
from forge.core.contracts.tasks import TaskSubmission
from forge.core.execution.bundle import JobBundle
from forge.tasks.vg_sopd.frontier_bundle_builder import VGFrontierBundleBuilder
from forge.tasks.vg_sopd.result_summary import summarize_vg_stage_result
from forge.tasks.vg_sopd.specs import FrontierTaskSpec


class VGFrontierPlugin:
    task_type = "vg_frontier"
    job_kind = JobKind.COLLECT

    def __init__(self, builder: VGFrontierBundleBuilder | None = None):
        self.builder = builder or VGFrontierBundleBuilder()

    def parse_request(self, raw: dict | FrontierTaskSpec) -> FrontierTaskSpec:
        return raw if isinstance(raw, FrontierTaskSpec) else FrontierTaskSpec.model_validate(raw)

    def validate_request(self, request: FrontierTaskSpec) -> list[str]:
        issues: list[str] = []
        if not request.task_source_path:
            issues.append("task_source_path is required")
        if not request.environments:
            issues.append("environments is required")
        return issues

    def build_bundle(self, *, bundle_dir: str, submission: TaskSubmission) -> JobBundle:
        request = self.parse_request(submission.task_request)
        issues = self.validate_request(request)
        if issues:
            raise ValueError(f"VG frontier request validation failed: {issues}")
        return self.builder.build(bundle_dir, spec=request, overwrite=True)

    def summarize_result(
        self,
        *,
        submission: TaskSubmission,
        bundle: JobBundle,
        status: RunStatus | None,
        manifest: ArtifactManifest | None,
    ) -> TaskSummary:
        return summarize_vg_stage_result(bundle=bundle, stage=self.task_type, status=status, manifest=manifest)


__all__ = ["VGFrontierPlugin"]
