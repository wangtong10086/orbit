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

from forge.core.control.service import CoreControlService
from forge.core.contracts.execution import RunHandle
from forge.core.contracts.tasks import TaskSubmission
from forge.core.contracts.templates import ExecutionOverrides
from forge.core.experiments import Experiment, TrainingLifecycleState
from forge.foundation.contracts import EvaluationSpec, TrainingSpec
from forge.pipeline.eval import EvaluationPipeline, EvalReport
from forge.pipeline.training import TrainingPipeline
from forge.tasks import build_default_task_registry
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
        control_plane: CoreControlService | None = None,
        evaluator: EvaluationPipeline | None = None,
        dataset_path_resolver: Callable[[Experiment], str | None] | None = None,
        template_id_resolver: Callable[[Experiment], str | None] | None = None,
        execution_overrides_resolver: Callable[[Experiment], ExecutionOverrides | None] | None = None,
        model_path_resolver: Callable[[Experiment, RunHandle], str | None] | None = None,
        bundle_dir_factory: Callable[[Experiment], str] | None = None,
        training_pipeline: TrainingPipeline | None = None,
    ):
        self.control_plane = control_plane or CoreControlService(
            bundle_dir_factory=bundle_dir_factory,
            task_registry=build_default_task_registry(),
        )
        self.evaluator = evaluator or EvaluationPipeline()
        self.dataset_path_resolver = dataset_path_resolver
        self.template_id_resolver = template_id_resolver
        self.execution_overrides_resolver = execution_overrides_resolver
        self.model_path_resolver = model_path_resolver
        self.bundle_dir_factory = bundle_dir_factory
        self.training_pipeline = training_pipeline or TrainingPipeline()

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
        issues = self.training_pipeline.validate_spec(training_spec)

        if not experiment.data_config:
            issues.append("No data_config specified")

        return issues

    def execute(self, experiment: Experiment) -> TrainingOutcome:
        """Launch training through real pipelines and only evaluate when a real model path is available."""
        issues = self.validate_experiment(experiment)
        if issues:
            raise ValueError(f"Experiment validation failed: {issues}")

        if self.template_id_resolver is None:
            return TrainingOutcome(
                status="blocked",
                reason="No execution template resolver configured",
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

        template_id = self.template_id_resolver(experiment)
        if not template_id:
            return TrainingOutcome(
                status="blocked",
                reason="No execution template available",
            )
        overrides = self.execution_overrides_resolver(experiment) if self.execution_overrides_resolver is not None else ExecutionOverrides()

        self.control_plane.save_experiment(experiment)
        launch = self.control_plane.submit_task(
            TaskSubmission(
                experiment_id=experiment.id,
                task_type="training",
                task_request=self.build_training_spec(experiment, dataset_path=dataset_path).model_dump(mode="json"),
                template_id=template_id,
                overrides=overrides,
                bundle_dir=self.bundle_dir_factory(experiment) if self.bundle_dir_factory else None,
            )
        )
        persisted = self.control_plane.load_experiment(experiment.id)
        if persisted is not None:
            persisted.status = TrainingLifecycleState.RUNNING
            self.control_plane.save_experiment(persisted, action="trainer_execute_submit")

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
