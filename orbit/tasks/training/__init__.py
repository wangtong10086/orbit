"""Training task plugin package."""

from orbit.tasks.training.plugin import TrainingPlugin
from orbit.tasks.training.specs import TrainingTaskSpec

__all__ = ["TrainingPlugin", "TrainingTaskSpec"]
