"""Trainer agent — automated training execution and evaluation.

Implements the "do" part of the training loop:
- Launch training with given config
- Monitor progress
- Run evaluation on checkpoints
- Select best checkpoint
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

from forge.foundation.contracts import EvaluationSpec, ExecutionProvider, TrainingLaunch, TrainingSpec
from forge.pipeline.eval import Evaluator, EvalReport
from forge.pipeline.experiment import Experiment
from forge.pipeline.training import TrainingPipeline
from forge.training.config import SwiftConfig


@dataclass
class TrainingOutcome:
    """Trainer result that distinguishes launched, blocked, and completed states."""

    status: str
    launch: TrainingLaunch | None = None
    eval_report: EvalReport | None = None
    reason: str = ""


class TrainerAgent:
    """Automated training agent — executes experiments.

    Usage:
        trainer = TrainerAgent()
        report = trainer.execute(experiment)
    """

    def __init__(
        self,
        evaluator: Evaluator | None = None,
        training_pipeline: TrainingPipeline | None = None,
        execution_provider: ExecutionProvider | None = None,
        model_path_resolver: Callable[[Experiment, TrainingLaunch], str | None] | None = None,
    ):
        self.evaluator = evaluator or Evaluator()
        self.training_pipeline = training_pipeline or TrainingPipeline()
        self.execution_provider = execution_provider
        self.model_path_resolver = model_path_resolver

    def build_training_spec(
        self,
        experiment: Experiment,
        dataset_path: str = "<dataset>",
    ) -> TrainingSpec:
        """Build the stable foundation training contract from an experiment."""
        tc = experiment.train_config
        config = SwiftConfig(**tc) if isinstance(tc, dict) else tc

        if experiment.data_config:
            environments = tuple(sorted(experiment.data_config.keys()))
        else:
            environments = tuple()

        return TrainingSpec(
            experiment_id=experiment.id,
            model=config.model,
            dataset_path=dataset_path,
            train_config=config.__dict__.copy(),
            environments=environments,
            output_dir=config.output_dir,
        )

    def validate_experiment(self, experiment: Experiment) -> list[str]:
        """Pre-flight check before training."""
        tc = experiment.train_config
        if not tc:
            return ["No train_config specified"]

        training_spec = self.build_training_spec(experiment)
        issues = self.training_pipeline.validate_spec(training_spec)

        if not experiment.data_config:
            issues.append("No data_config specified")

        return issues

    def execute(self, experiment: Experiment) -> TrainingOutcome:
        """Launch training through real pipelines and only evaluate when a real model path is available."""
        issues = self.validate_experiment(experiment)
        if issues:
            raise ValueError(f"Experiment validation failed: {issues}")

        if self.execution_provider is None:
            return TrainingOutcome(
                status="blocked",
                reason="No execution provider configured",
            )

        training_spec = self.build_training_spec(experiment)
        launch = asyncio.run(
            self.training_pipeline.launch(training_spec, self.execution_provider)
        )

        if self.model_path_resolver is None:
            return TrainingOutcome(
                status="launched",
                launch=launch,
                reason="Training launched; no evaluation model path resolver configured",
            )

        model_path = self.model_path_resolver(experiment, launch)
        if not model_path:
            return TrainingOutcome(
                status="launched",
                launch=launch,
                reason="Training launched; evaluation model path unavailable",
            )

        eval_report = self.evaluator.run_evaluation(
            EvaluationSpec(
                model_path=model_path,
                environments=training_spec.environments,
            )
        )
        return TrainingOutcome(
            status="completed",
            launch=launch,
            eval_report=eval_report,
        )
