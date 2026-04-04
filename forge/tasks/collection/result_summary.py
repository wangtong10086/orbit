"""Collection result summarization."""

from __future__ import annotations

import json

from forge.core.contracts.execution import ArtifactManifest, RunStatus
from forge.core.contracts.results import TaskSummary
from forge.core.execution.bundle import JobBundle


def summarize_collection_result(*, bundle: JobBundle, status: RunStatus | None, manifest: ArtifactManifest | None) -> TaskSummary:
    summary: TaskSummary = {
        "bundle_path": str(bundle.path),
        "status": status.state.value if status is not None else "",
    }
    publish_path = bundle.artifacts_dir / "publish_result.json"
    if publish_path.exists():
        try:
            payload = json.loads(publish_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        summary["publish_result"] = "artifacts/publish_result.json"
        if isinstance(payload, dict):
            collect = payload.get("collect", {})
            ingest = payload.get("ingest", {})
            if isinstance(collect, dict) and "records" in collect:
                summary["records"] = collect["records"]
            if isinstance(ingest, dict) and "new_total" in ingest:
                summary["new_total"] = ingest["new_total"]
    if manifest is not None:
        summary["artifacts"] = dict(manifest.artifacts)
        summary["logs"] = dict(manifest.logs)
    return summary
