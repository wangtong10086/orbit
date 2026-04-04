"""Execution-template contracts."""

from __future__ import annotations

from pydantic import Field

from forge.core.contracts.execution import (
    EnvKey,
    ExecutionRequest,
    LaunchModeKind,
    LaunchModeSpec,
    PlacementKind,
    PlacementSpec,
    ResourceRequest,
)
from forge.foundation.schema import FrozenModel, JsonValue, RequestContext


class ExecutionTemplateDefaults(FrozenModel):
    image: str = ""
    target: str = ""
    detach: bool = True
    resources: ResourceRequest = Field(default_factory=ResourceRequest)
    runtime_env: dict[EnvKey, str] = Field(default_factory=dict)


class ExecutionTemplate(FrozenModel):
    id: str
    description: str = ""
    placement: PlacementSpec
    launch_mode: LaunchModeSpec
    defaults: ExecutionTemplateDefaults = Field(default_factory=ExecutionTemplateDefaults)
    allow_overrides: tuple[str, ...] = ("image", "target", "resources", "runtime_env", "detach")
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class ExecutionOverrides(FrozenModel):
    image: str = ""
    target: str = ""
    detach: bool | None = None
    resources: ResourceRequest | None = None
    runtime_env: dict[EnvKey, str] = Field(default_factory=dict)


def resolve_execution_request(
    *,
    template: ExecutionTemplate,
    bundle_path: str,
    overrides: ExecutionOverrides | None = None,
    context: RequestContext | None = None,
) -> ExecutionRequest:
    overrides = overrides or ExecutionOverrides()
    resolved_image = template.defaults.image
    resolved_target = template.defaults.target
    resolved_detach = template.defaults.detach
    resolved_resources = template.defaults.resources
    resolved_runtime_env = dict(template.defaults.runtime_env)
    if "image" in template.allow_overrides and overrides.image:
        resolved_image = overrides.image
    if "target" in template.allow_overrides and overrides.target:
        resolved_target = overrides.target
    if "detach" in template.allow_overrides and overrides.detach is not None:
        resolved_detach = overrides.detach
    if "resources" in template.allow_overrides and overrides.resources is not None:
        resolved_resources = overrides.resources
    if "runtime_env" in template.allow_overrides:
        resolved_runtime_env.update(overrides.runtime_env)

    return ExecutionRequest(
        bundle_path=bundle_path,
        placement=template.placement.model_copy(update={"target": resolved_target or template.placement.target}),
        launch_mode=template.launch_mode.model_copy(update={"image": resolved_image or template.launch_mode.image, "detach": resolved_detach}),
        resources=resolved_resources,
        runtime_env=resolved_runtime_env,
        context=context or RequestContext(),
    )


def validate_public_template(template: ExecutionTemplate) -> None:
    return None
