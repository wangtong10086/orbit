"""Compatibility re-exports for execution templates moved into forge.core."""

from forge.core.contracts.templates import ExecutionOverrides, ExecutionTemplate, ExecutionTemplateDefaults
from forge.core.templates.registry import ExecutionTemplateRegistry

__all__ = [
    "ExecutionOverrides",
    "ExecutionTemplate",
    "ExecutionTemplateDefaults",
    "ExecutionTemplateRegistry",
]
