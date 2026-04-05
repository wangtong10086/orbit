"""Compatibility facade over the generic core control kernel."""

from __future__ import annotations

from orbit.control.contracts import (
    PrepareCollectRequest,
    PrepareEvalRequest,
    PrepareTrainRequest,
    RunLogsQuery,
    RunQuery,
    SubmitCollectRequest,
    SubmitEvalRequest,
    SubmitTrainRequest,
)
from orbit.core.control.service import CoreControlService
from orbit.core.contracts.execution import JobKind, RunState
from orbit.core.contracts.tasks import TaskSubmission
from orbit.core.experiments.models import Experiment, TrainingLifecycleState
from orbit.execution.bundle import JobBundle
from orbit.execution.contracts import ArtifactManifest, RunHandle, RunStatus
from orbit.foundation.contracts import TrainingSpec
from orbit.pipeline.eval import EvaluationPipeline
from orbit.pipeline.training import TrainingPipeline
from orbit.tasks import build_default_task_registry
from orbit.training.config import SwiftConfig


class ControlPlane(CoreControlService):
    """Legacy task-aware facade backed by the generic plugin-based control kernel."""

    def __init__(
        self,
        experiments=None,
        training: TrainingPipeline | None = None,
        evaluation: EvaluationPipeline | None = None,
        execution=None,
        templates=None,
        bundle_dir_factory=None,
        audit=None,
        task_registry=None,
    ):
        self.training = training or TrainingPipeline()
        self.evaluation = evaluation or EvaluationPipeline()
        super().__init__(
            experiments=experiments,
            execution=execution,
            templates=templates,
            task_registry=task_registry or build_default_task_registry(),
            bundle_dir_factory=bundle_dir_factory,
            audit=audit,
        )

    def prepare_training_bundle(self, request: PrepareTrainRequest) -> JobBundle:
        experiment = self._require_experiment(request.experiment_id)
        bundle = self.prepare_task(
            TaskSubmission(
                experiment_id=request.experiment_id,
                task_type="training",
                task_request=self._build_training_spec(experiment, request.dataset_path).model_dump(mode="json"),
                template_id="",
                bundle_dir=request.bundle_dir,
                context=request.context,
            )
        )
        experiment = self._require_experiment(request.experiment_id)
        experiment.status = TrainingLifecycleState.PREPARED
        self.save_experiment(experiment, context=request.context, action="prepare_training_bundle")
        return bundle

    def submit_training(self, request: SubmitTrainRequest) -> RunHandle:
        experiment = self._require_experiment(request.experiment_id)
        handle = self.submit_task(
            TaskSubmission(
                experiment_id=request.experiment_id,
                task_type="training",
                task_request=self._build_training_spec(experiment, request.dataset_path).model_dump(mode="json"),
                template_id=request.template_id,
                overrides=request.overrides,
                bundle_dir=request.bundle_dir,
                context=request.context,
            )
        )
        experiment = self._require_experiment(request.experiment_id)
        experiment.status = TrainingLifecycleState.RUNNING
        self.save_experiment(experiment, context=request.context, action="submit_training")
        return handle

    def prepare_eval_bundle(self, request: PrepareEvalRequest) -> JobBundle:
        return self.prepare_task(
            TaskSubmission(
                experiment_id=request.experiment_id,
                task_type="evaluation",
                task_request=request.spec.model_dump(mode="json"),
                template_id="",
                bundle_dir=request.bundle_dir,
                context=request.context,
            )
        )

    def submit_eval(self, request: SubmitEvalRequest) -> RunHandle:
        return self.submit_task(
            TaskSubmission(
                experiment_id=request.experiment_id,
                task_type="evaluation",
                task_request=request.spec.model_dump(mode="json"),
                template_id=request.template_id,
                overrides=request.overrides,
                bundle_dir=request.bundle_dir,
                context=request.context,
            )
        )

    def prepare_collect_bundle(self, request: PrepareCollectRequest) -> JobBundle:
        return self.prepare_task(
            TaskSubmission(
                experiment_id=request.experiment_id,
                task_type="collection",
                task_request=request.spec.model_dump(mode="json"),
                template_id="",
                bundle_dir=request.bundle_dir,
                context=request.context,
            )
        )

    def submit_collect(self, request: SubmitCollectRequest) -> RunHandle:
        return self.submit_task(
            TaskSubmission(
                experiment_id=request.experiment_id,
                task_type="collection",
                task_request=request.spec.model_dump(mode="json"),
                template_id=request.template_id,
                overrides=request.overrides,
                bundle_dir=request.bundle_dir,
                context=request.context,
            )
        )

    def refresh_run_status(self, request: RunQuery) -> RunStatus:
        status = super().refresh_run_status(request)
        if request.run_kind == JobKind.TRAIN and status.state in {RunState.SUCCEEDED, RunState.FAILED, RunState.TERMINATED}:
            experiment = self._require_experiment(request.experiment_id)
            experiment.status = {
                RunState.SUCCEEDED: TrainingLifecycleState.COMPLETED,
                RunState.FAILED: TrainingLifecycleState.FAILED,
                RunState.TERMINATED: TrainingLifecycleState.TERMINATED,
            }[status.state]
            self.save_experiment(experiment, context=request.context, action="refresh_run_status_training_state")
        return status

    def collect_run_artifacts(self, request: RunQuery) -> ArtifactManifest:
        return super().collect_run_artifacts(request)

    def read_run_logs(self, request: RunLogsQuery) -> str:
        return super().read_run_logs(request)

    def terminate_run(self, request: RunQuery) -> None:
        super().terminate_run(request)
        if request.run_kind == JobKind.TRAIN:
            experiment = self._require_experiment(request.experiment_id)
            experiment.status = TrainingLifecycleState.TERMINATED
            self.save_experiment(experiment, context=request.context, action="terminate_training_run")

    def _build_training_spec(self, experiment: Experiment, dataset_path: str) -> TrainingSpec:
        config = SwiftConfig.model_validate(experiment.train_config)
        environments = tuple(sorted(experiment.data_config.keys())) if experiment.data_config else tuple()
        return TrainingSpec(
            experiment_id=experiment.id,
            model=config.model,
            dataset_path=dataset_path,
            train_config=config,
            environments=environments,
            output_dir=config.output_dir,
        )
