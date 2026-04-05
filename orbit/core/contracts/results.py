"""Task-result contracts."""

from __future__ import annotations

from pydantic import Field

from orbit.foundation.schema import FrozenModel, JsonValue

TaskSummary = dict[str, JsonValue]


class TaskResultEnvelope(FrozenModel):
    task_type: str
    summary: dict[str, JsonValue] = Field(default_factory=dict)
