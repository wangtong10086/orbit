"""Task plugin for the VG-SOPD compiler stage."""

from __future__ import annotations

from forge.core.contracts.execution import ArtifactManifest, JobKind, RunStatus
from forge.core.contracts.results import TaskSummary
from forge.core.contracts.tasks import TaskSubmission
from forge.core.execution.bundle import JobBundle
from forge.tasks.vg_sopd.compile_bundle_builder import VGCompileBundleBuilder
from forge.tasks.vg_sopd.result_summary import summarize_vg_stage_result
from forge.tasks.vg_sopd.specs import CompileTaskSpec


class VGCompilePlugin:
    task_type = "vg_compile"
    job_kind = JobKind.COLLECT

    def __init__(self, builder: VGCompileBundleBuilder | None = None):
        self.builder = builder or VGCompileBundleBuilder()

    def parse_request(self, raw: dict | CompileTaskSpec) -> CompileTaskSpec:
        return raw if isinstance(raw, CompileTaskSpec) else CompileTaskSpec.model_validate(raw)

    def validate_request(self, request: CompileTaskSpec) -> list[str]:
        issues: list[str] = []
        if not request.relabelled_traces_path:
            issues.append("relabelled_traces_path is required")
        if not request.teacher_augmented_traces_path:
            issues.append("teacher_augmented_traces_path is required")
        return issues

    def build_bundle(self, *, bundle_dir: str, submission: TaskSubmission) -> JobBundle:
        request = self.parse_request(submission.task_request)
        issues = self.validate_request(request)
        if issues:
            raise ValueError(f"VG compile request validation failed: {issues}")
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


__all__ = ["VGCompilePlugin"]
