"""Result summarization helpers for VG-SOPD stage tasks."""

from __future__ import annotations

from forge.core.contracts.execution import ArtifactManifest, RunStatus
from forge.core.contracts.results import TaskSummary
from forge.core.execution.bundle import JobBundle


def summarize_vg_stage_result(*, bundle: JobBundle, stage: str, status: RunStatus | None, manifest: ArtifactManifest | None) -> TaskSummary:
    summary: TaskSummary = {
        "bundle_path": str(bundle.path),
        "stage": stage,
        "status": status.state.value if status is not None else "",
    }
    if manifest is not None:
        summary["artifacts"] = dict(manifest.artifacts)
        summary["logs"] = dict(manifest.logs)
    return summary


__all__ = ["summarize_vg_stage_result"]
