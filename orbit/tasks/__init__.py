"""Task plugin registry wiring."""

from orbit.tasks.registry import TaskRegistry
from orbit.tasks.training.plugin import TrainingPlugin
from orbit.tasks.evaluation.plugin import EvaluationPlugin
from orbit.tasks.collection.plugin import CollectionPlugin
from orbit.tasks.vg_sopd import VGCompilePlugin, VGFrontierPlugin, VGRelabelPlugin


def build_default_task_registry() -> TaskRegistry:
    registry = TaskRegistry()
    registry.register(TrainingPlugin())
    registry.register(EvaluationPlugin())
    registry.register(CollectionPlugin())
    registry.register(VGFrontierPlugin())
    registry.register(VGRelabelPlugin())
    registry.register(VGCompilePlugin())
    return registry


__all__ = [
    "TaskRegistry",
    "build_default_task_registry",
]
