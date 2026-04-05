"""Evaluation result summarization."""

from __future__ import annotations

from orbit.core.contracts.execution import ArtifactManifest, RunStatus
from orbit.core.contracts.results import TaskSummary
from orbit.core.execution.bundle import JobBundle


def summarize_evaluation_result(*, bundle: JobBundle, status: RunStatus | None, manifest: ArtifactManifest | None) -> TaskSummary:
    summary: TaskSummary = {
        "bundle_path": str(bundle.path),
        "status": status.state.value if status is not None else "",
    }
    if manifest is not None:
        if "eval_summary.json" in manifest.artifacts:
            summary["eval_summary"] = manifest.artifacts["eval_summary.json"]
        summary["artifacts"] = dict(manifest.artifacts)
    return summary
