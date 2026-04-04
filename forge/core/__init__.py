"""Core kernel package."""

__all__ = [
    "CoreControlService",
    "ExecutionOverrides",
    "ExecutionTemplate",
    "ExecutionTemplateRegistry",
    "Experiment",
    "ExperimentResults",
    "ExperimentStore",
    "RunRecord",
    "TrainingLifecycleState",
]


def __getattr__(name: str):
    if name == "CoreControlService":
        from forge.core.control.service import CoreControlService

        return CoreControlService
    if name in {"Experiment", "ExperimentResults", "RunRecord", "TrainingLifecycleState"}:
        from forge.core.experiments.models import Experiment, ExperimentResults, RunRecord, TrainingLifecycleState

        return {
            "Experiment": Experiment,
            "ExperimentResults": ExperimentResults,
            "RunRecord": RunRecord,
            "TrainingLifecycleState": TrainingLifecycleState,
        }[name]
    if name == "ExperimentStore":
        from forge.core.experiments.store import ExperimentStore

        return ExperimentStore
    if name in {"ExecutionOverrides", "ExecutionTemplate"}:
        from forge.core.contracts.templates import ExecutionOverrides, ExecutionTemplate

        return {"ExecutionOverrides": ExecutionOverrides, "ExecutionTemplate": ExecutionTemplate}[name]
    if name == "ExecutionTemplateRegistry":
        from forge.core.templates.registry import ExecutionTemplateRegistry

        return ExecutionTemplateRegistry
    raise AttributeError(name)
