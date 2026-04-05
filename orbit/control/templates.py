"""Compatibility re-exports for execution templates moved into orbit.core."""

from orbit.core.contracts.templates import ExecutionOverrides, ExecutionTemplate, ExecutionTemplateDefaults
from orbit.core.templates.registry import ExecutionTemplateRegistry

__all__ = [
    "ExecutionOverrides",
    "ExecutionTemplate",
    "ExecutionTemplateDefaults",
    "ExecutionTemplateRegistry",
]
