"""Plugin protocols and explicit registries for the generic control kernel."""

from __future__ import annotations

from typing import Any, Protocol

from forge.core.contracts.execution import ArtifactManifest, JobKind, RunStatus
from forge.core.contracts.results import TaskSummary
from forge.core.contracts.tasks import TaskSubmission
from forge.core.execution.bundle import JobBundle


class TaskPlugin(Protocol):
    task_type: str
    job_kind: JobKind

    def parse_request(self, raw: dict | Any) -> Any:
        ...

    def validate_request(self, request: Any) -> list[str]:
        ...

    def build_bundle(
        self,
        *,
        bundle_dir: str,
        submission: TaskSubmission,
    ) -> JobBundle:
        ...

    def summarize_result(
        self,
        *,
        submission: TaskSubmission,
        bundle: JobBundle,
        status: RunStatus | None,
        manifest: ArtifactManifest | None,
    ) -> TaskSummary:
        ...


class TaskRegistry:
    def __init__(self):
        self._plugins: dict[str, TaskPlugin] = {}

    def register(self, plugin: TaskPlugin) -> None:
        if plugin.task_type in self._plugins:
            raise ValueError(f"Task plugin already registered: {plugin.task_type}")
        self._plugins[plugin.task_type] = plugin

    def get(self, task_type: str) -> TaskPlugin:
        try:
            return self._plugins[task_type]
        except KeyError as exc:
            raise ValueError(f"Unknown task type: {task_type}") from exc

    def list_task_types(self) -> list[str]:
        return sorted(self._plugins)


__all__ = ["TaskPlugin", "TaskRegistry"]
