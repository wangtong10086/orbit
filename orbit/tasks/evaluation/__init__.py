"""Evaluation task plugin package."""

from orbit.tasks.evaluation.plugin import EvaluationPlugin
from orbit.tasks.evaluation.specs import EvalTaskSpec

__all__ = ["EvaluationPlugin", "EvalTaskSpec"]
