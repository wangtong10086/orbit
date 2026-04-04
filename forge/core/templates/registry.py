"""Execution template registry for the core control kernel."""

from __future__ import annotations

from pathlib import Path

import yaml

from forge.core.contracts.execution import ExecutionRequest
from forge.core.contracts.templates import ExecutionOverrides, ExecutionTemplate, resolve_execution_request, validate_public_template
from forge.foundation.schema import RequestContext


class ExecutionTemplateRegistry:
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
                validate_public_template(self._load_path(path))
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
        validate_public_template(template)
        request = resolve_execution_request(
            template=template,
            bundle_path=bundle_path,
            overrides=overrides,
            context=context,
        )
        return template, request

    def _load_path(self, path: Path) -> ExecutionTemplate:
        with path.open(encoding="utf-8") as handle:
            return ExecutionTemplate.model_validate(yaml.safe_load(handle) or {})
