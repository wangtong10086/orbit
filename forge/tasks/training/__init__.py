"""Training task plugin package."""

from forge.tasks.training.plugin import TrainingPlugin
from forge.tasks.training.specs import TrainingTaskSpec

__all__ = ["TrainingPlugin", "TrainingTaskSpec"]
