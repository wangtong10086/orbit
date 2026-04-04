"""Training result summarization."""

from __future__ import annotations

from forge.core.contracts.execution import ArtifactManifest, RunStatus
from forge.core.contracts.results import TaskSummary
from forge.core.execution.bundle import JobBundle


def summarize_training_result(*, bundle: JobBundle, status: RunStatus | None, manifest: ArtifactManifest | None) -> TaskSummary:
    summary: TaskSummary = {
        "bundle_path": str(bundle.path),
        "status": status.state.value if status is not None else "",
    }
    if manifest is not None:
        if "checkpoints" in manifest.artifacts:
            summary["checkpoints"] = manifest.artifacts["checkpoints"]
        if "training.log" in manifest.logs:
            summary["training_log"] = manifest.logs["training.log"]
    return summary
