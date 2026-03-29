"""Trainer agent — automated training execution and evaluation.

Implements the "do" part of the training loop:
- Launch training with given config
- Monitor progress
- Run evaluation on checkpoints
- Select best checkpoint
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from forge.control import ControlPlane, ControlSubmissionTarget
from forge.control.contracts import SubmitTrainRequest
from forge.control.experiment import Experiment
from forge.execution.contracts import RunHandle
from forge.foundation.contracts import EvaluationSpec, TrainingSpec
from forge.pipeline.eval import EvaluationPipeline, EvalReport
from forge.training.config import SwiftConfig


@dataclass
class TrainingOutcome:
    """Trainer result that distinguishes launched, blocked, and completed states."""

    status: str
    launch: RunHandle | None = None
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
        control_plane: ControlPlane | None = None,
        evaluator: EvaluationPipeline | None = None,
        dataset_path_resolver: Callable[[Experiment], str | None] | None = None,
        submission_target_resolver: Callable[[Experiment], ControlSubmissionTarget | None] | None = None,
        model_path_resolver: Callable[[Experiment, RunHandle], str | None] | None = None,
        bundle_dir_factory: Callable[[Experiment], str] | None = None,
    ):
        self.control_plane = control_plane or ControlPlane(bundle_dir_factory=bundle_dir_factory)
        self.evaluator = evaluator or self.control_plane.evaluation
        self.dataset_path_resolver = dataset_path_resolver
        self.submission_target_resolver = submission_target_resolver
        self.model_path_resolver = model_path_resolver
        self.bundle_dir_factory = bundle_dir_factory

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
            train_config=config,
            environments=environments,
            output_dir=config.output_dir,
        )

    def validate_experiment(self, experiment: Experiment) -> list[str]:
        """Pre-flight check before training."""
        tc = experiment.train_config
        if not tc:
            return ["No train_config specified"]

        training_spec = self.build_training_spec(experiment)
        issues = self.control_plane.training.validate_spec(training_spec)

        if not experiment.data_config:
            issues.append("No data_config specified")

        return issues

    def execute(self, experiment: Experiment) -> TrainingOutcome:
        """Launch training through real pipelines and only evaluate when a real model path is available."""
        issues = self.validate_experiment(experiment)
        if issues:
            raise ValueError(f"Experiment validation failed: {issues}")

        if self.submission_target_resolver is None:
            return TrainingOutcome(
                status="blocked",
                reason="No submission target resolver configured",
            )

        if self.dataset_path_resolver is None:
            return TrainingOutcome(
                status="blocked",
                reason="No dataset path resolver configured",
            )

        dataset_path = self.dataset_path_resolver(experiment)
        if not dataset_path:
            return TrainingOutcome(
                status="blocked",
                reason="Training dataset path unavailable",
            )

        submission_target = self.submission_target_resolver(experiment)
        if submission_target is None:
            return TrainingOutcome(
                status="blocked",
                reason="No submission target available",
            )

        self.control_plane.save_experiment(experiment)
        launch = self.control_plane.submit_training(
            SubmitTrainRequest(
                experiment_id=experiment.id,
                dataset_path=dataset_path,
                submission_target=submission_target,
                bundle_dir=self.bundle_dir_factory(experiment) if self.bundle_dir_factory else None,
            )
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

        training_spec = self.build_training_spec(experiment, dataset_path=dataset_path)
        eval_report = self.evaluator.run_evaluation(
            EvaluationSpec(
                model_path=model_path,
                environments=training_spec.environments,
            )
        )
        self.control_plane.record_agent_evaluation(experiment.id, eval_report)
        return TrainingOutcome(
            status="completed",
            launch=launch,
            eval_report=eval_report,
        )
