"""Generic task submission contracts."""

from __future__ import annotations

from pydantic import Field

from forge.core.contracts.templates import ExecutionOverrides
from forge.foundation.schema import FrozenModel, JsonValue, RequestContext


class TaskSubmission(FrozenModel):
    experiment_id: str
    task_type: str
    task_request: dict[str, JsonValue]
    template_id: str
    overrides: ExecutionOverrides = Field(default_factory=ExecutionOverrides)
    bundle_dir: str | None = None
    context: RequestContext = Field(default_factory=RequestContext)
