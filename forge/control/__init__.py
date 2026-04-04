"""Control-plane package."""

from forge.control.experiment import Experiment, ExperimentStore
from forge.control.templates import ExecutionOverrides, ExecutionTemplate, ExecutionTemplateRegistry

__all__ = [
    "ControlPlane",
    "ExecutionOverrides",
    "ExecutionTemplate",
    "ExecutionTemplateRegistry",
    "Experiment",
    "ExperimentStore",
]


def __getattr__(name: str):
    if name == "ControlPlane":
        from forge.control.service import ControlPlane

        return ControlPlane
    raise AttributeError(name)
