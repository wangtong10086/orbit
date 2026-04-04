"""Evaluation task plugin package."""

from forge.tasks.evaluation.plugin import EvaluationPlugin
from forge.tasks.evaluation.specs import EvalTaskSpec

__all__ = ["EvaluationPlugin", "EvalTaskSpec"]
