"""Task plugin for the VG-SOPD relabel stage."""

from __future__ import annotations

from forge.core.contracts.execution import ArtifactManifest, JobKind, RunStatus
from forge.core.contracts.results import TaskSummary
from forge.core.contracts.tasks import TaskSubmission
from forge.core.execution.bundle import JobBundle
from forge.tasks.vg_sopd.relabel_bundle_builder import VGRelabelBundleBuilder
from forge.tasks.vg_sopd.result_summary import summarize_vg_stage_result
from forge.tasks.vg_sopd.specs import RelabelTaskSpec


class VGRelabelPlugin:
    task_type = "vg_relabel"
    job_kind = JobKind.COLLECT

    def __init__(self, builder: VGRelabelBundleBuilder | None = None):
        self.builder = builder or VGRelabelBundleBuilder()

    def parse_request(self, raw: dict | RelabelTaskSpec) -> RelabelTaskSpec:
        return raw if isinstance(raw, RelabelTaskSpec) else RelabelTaskSpec.model_validate(raw)

    def validate_request(self, request: RelabelTaskSpec) -> list[str]:
        issues: list[str] = []
        if not request.frontier_traces_path:
            issues.append("frontier_traces_path is required")
        return issues

    def build_bundle(self, *, bundle_dir: str, submission: TaskSubmission) -> JobBundle:
        request = self.parse_request(submission.task_request)
        issues = self.validate_request(request)
        if issues:
            raise ValueError(f"VG relabel request validation failed: {issues}")
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


__all__ = ["VGRelabelPlugin"]
