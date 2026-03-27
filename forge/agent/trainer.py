"""Trainer agent — automated training execution and evaluation.

Implements the "do" part of the training loop:
- Launch training with given config
- Monitor progress
- Run evaluation on checkpoints
- Select best checkpoint
"""

from __future__ import annotations

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

        # Build training command
        tc = experiment.train_config
        config = SwiftConfig(**tc) if isinstance(tc, dict) else tc
        self.backend.generate_command(config, dataset_path="<dataset>")

        # Actual execution would happen via executor
        # For now return empty report
        return EvalReport(model_path=f"checkpoints/{experiment.id}")
