"""Trainer agent — automated training execution and evaluation.

Implements the "do" part of the training loop:
- Launch training with given config
- Monitor progress
- Run evaluation on checkpoints
- Select best checkpoint
"""

from __future__ import annotations

from forge.foundation.contracts import EvaluationSpec, TrainingSpec
from forge.pipeline.eval import Evaluator, EvalReport
from forge.pipeline.experiment import Experiment
from forge.training.sft import SwiftBackend
from forge.training.config import SwiftConfig


class TrainerAgent:
    """Automated training agent — executes experiments.

    Usage:
        trainer = TrainerAgent()
        report = trainer.execute(experiment)
    """

    def __init__(self, evaluator: Evaluator | None = None):
        self.evaluator = evaluator or Evaluator()
        self.backend = SwiftBackend()

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
        issues = []

        tc = experiment.train_config
        if not tc:
            issues.append("No train_config specified")
            return issues

        # Build SwiftConfig and validate
        config = SwiftConfig(**tc) if isinstance(tc, dict) else tc
        issues.extend(self.backend.validate_config(config))

        # Check data config
        dc = experiment.data_config
        if not dc:
            issues.append("No data_config specified")

        return issues

    def execute(self, experiment: Experiment) -> EvalReport:
        """Execute the full training → evaluation pipeline.

        1. Validate config
        2. Generate training script
        3. Launch training (via executor)
        4. Wait for completion
        5. Run evaluation
        6. Return report

        Note: Steps 2-4 require a running executor (Targon/SSH).
        This method provides the orchestration interface.
        """
        # Validate first
        issues = self.validate_experiment(experiment)
        if issues:
            raise ValueError(f"Experiment validation failed: {issues}")

        training_spec = self.build_training_spec(experiment)
        config = SwiftConfig(**training_spec.train_config)
        self.backend.generate_command(config, dataset_path=training_spec.dataset_path)

        # Actual execution would happen via executor
        # For now return empty report
        return self.evaluator.run_evaluation(
            EvaluationSpec(
                model_path=f"{training_spec.output_dir.rstrip('/')}/{experiment.id}",
                environments=training_spec.environments,
            )
        )
