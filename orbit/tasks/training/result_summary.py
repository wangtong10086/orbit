"""Training result summarization."""

from __future__ import annotations

from orbit.core.contracts.execution import ArtifactManifest, RunStatus
from orbit.core.contracts.results import TaskSummary
from orbit.core.execution.bundle import JobBundle


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
        if "rollout.log" in manifest.logs:
            summary["rollout_log"] = manifest.logs["rollout.log"]
        if "runtime-precheck.log" in manifest.logs:
            summary["runtime_precheck_log"] = manifest.logs["runtime-precheck.log"]
    return summary
