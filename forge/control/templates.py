"""Execution template registry for the control plane."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field

from forge.execution.contracts import (
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


class ExecutionTemplateRegistry:
    """YAML-backed execution-template registry."""

    def __init__(self, templates_dir: str = "execution_templates"):
        self.dir = Path(templates_dir)

    def list_templates(self) -> list[ExecutionTemplate]:
        if not self.dir.exists():
            return []
        templates: list[ExecutionTemplate] = []
        for path in sorted(self.dir.glob("*.yaml")):
            templates.append(self._load_path(path))
        return templates

    def load(self, template_id: str) -> ExecutionTemplate:
        for path in (self.dir / f"{template_id}.yaml", self.dir / f"{template_id}.yml"):
            if path.exists():
                return self._load_path(path)
        raise ValueError(f"Unknown execution template: {template_id}")

    def validate(self) -> list[str]:
        issues: list[str] = []
        for path in sorted(self.dir.glob("*.yaml")):
            try:
                self._validate_template(self._load_path(path))
            except Exception as exc:
                issues.append(f"{path.name}: {exc}")
        return issues

    def resolve(
        self,
        *,
        template_id: str,
        bundle_path: str,
        overrides: ExecutionOverrides | None = None,
        context: RequestContext | None = None,
    ) -> tuple[ExecutionTemplate, ExecutionRequest]:
        template = self.load(template_id)
        self._validate_template(template)
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

        request = ExecutionRequest(
            bundle_path=bundle_path,
            placement=template.placement.model_copy(update={"target": resolved_target or template.placement.target}),
            launch_mode=template.launch_mode.model_copy(update={"image": resolved_image or template.launch_mode.image, "detach": resolved_detach}),
            resources=resolved_resources,
            runtime_env=resolved_runtime_env,
            context=context or RequestContext(),
        )
        return template, request

    def _load_path(self, path: Path) -> ExecutionTemplate:
        with path.open(encoding="utf-8") as handle:
            return ExecutionTemplate.model_validate(yaml.safe_load(handle) or {})

    def _validate_template(self, template: ExecutionTemplate) -> None:
        if template.placement.kind == PlacementKind.TARGON_RENTAL and template.launch_mode.kind == LaunchModeKind.HOST_PROCESS:
            raise ValueError("public templates must not expose targon_rental + host_process")
