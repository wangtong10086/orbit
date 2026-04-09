"""Task plugin registry wiring."""

from orbit.tasks.registry import TaskRegistry


def build_default_task_registry() -> TaskRegistry:
    from orbit.tasks.collection.plugin import CollectionPlugin
    from orbit.tasks.evaluation.plugin import EvaluationPlugin
    from orbit.tasks.training.plugin import TrainingPlugin

    registry = TaskRegistry()
    registry.register(TrainingPlugin())
    registry.register(EvaluationPlugin())
    registry.register(CollectionPlugin())
    return registry


__all__ = [
    "TaskRegistry",
    "build_default_task_registry",
]
