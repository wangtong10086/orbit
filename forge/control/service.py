"""Control-plane orchestration over experiment state and execution-plane runtimes."""

from __future__ import annotations

import asyncio
import tempfile
import time

from forge.control.bundles import CollectBundleBuilder, EvalBundleBuilder
from forge.control.contracts import (
    CreateExperimentRequest,
    PrepareCollectRequest,
    PrepareEvalRequest,
    PrepareTrainRequest,
    RunLogsQuery,
    RunQuery,
    SubmitCollectRequest,
    SubmitEvalRequest,
    SubmitTrainRequest,
    run_record_key,
)
from forge.control.experiment import (
    AgentEvaluationRecord,
    Experiment,
    ExperimentResults,
    ExperimentStore,
    RunRecord,
    TrainingLifecycleState,
)
from forge.control.templates import ExecutionTemplateRegistry
from forge.execution.bundle import JobBundle
from forge.execution.contracts import (
    ArtifactManifest,
    CollectArtifactsRequest,
    JobKind,
    RunHandle,
    RunLogsRequest,
    RunStatus,
    RunStatusRequest,
    TerminateRunRequest,
)
from forge.execution.service import ExecutionService
from forge.foundation.audit import AuditEvent, AuditWriter
from forge.foundation.contracts import TrainingSpec
from forge.foundation.schema import RequestContext
from forge.pipeline.eval import EvaluationPipeline
from forge.pipeline.training import TrainingPipeline
from forge.training.config import SwiftConfig


class ControlPlane:
    """High-level control-plane service."""

    def __init__(
        self,
        experiments: ExperimentStore | None = None,
        training: TrainingPipeline | None = None,
        evaluation: EvaluationPipeline | None = None,
        execution: ExecutionService | None = None,
        templates: ExecutionTemplateRegistry | None = None,
        bundle_dir_factory=None,
        audit: AuditWriter | None = None,
    ):
        self.experiments = experiments or ExperimentStore()
        self.training = training or TrainingPipeline()
        self.evaluation = evaluation or EvaluationPipeline()
        self.eval_builder = EvalBundleBuilder()
        self.collect_builder = CollectBundleBuilder()
        self.execution = execution
        self.templates = templates or ExecutionTemplateRegistry()
        self.bundle_dir_factory = bundle_dir_factory or (lambda experiment: tempfile.mkdtemp(prefix=f"forge-control-{experiment.id}-"))
        self.audit = audit or AuditWriter()

    def list_experiments(self, status: str | None = None) -> list[Experiment]:
        return self.experiments.list_experiments(status=status)

    def load_experiment(self, experiment_id: str) -> Experiment | None:
        return self.experiments.load(experiment_id)

    def create_experiment(self, request: CreateExperimentRequest) -> Experiment:
        actual_id = request.experiment_id or self.experiments.next_experiment_id()
        if self.experiments.exists(actual_id):
            raise ValueError(f"Experiment already exists: {actual_id}")
        experiment = Experiment(
            id=actual_id,
            variable=request.variable,
            hypothesis=request.hypothesis,
            status=TrainingLifecycleState(request.status),
            train_config=request.train_config,
            data_config=request.data_config,
            notes=request.notes,
            results=ExperimentResults(),
        )
        self.experiments.save(experiment)
        self._audit_experiment("create_experiment", request.context, experiment, request=request)
        return experiment

    def save_experiment(self, experiment: Experiment, *, context: RequestContext | None = None, action: str = "save_experiment") -> None:
        self.experiments.save(experiment)
        self._audit_experiment(action, context or RequestContext(), experiment)

    def update_status(self, experiment_id: str, status: str, *, context: RequestContext | None = None) -> bool:
        experiment = self.load_experiment(experiment_id)
        if experiment is None:
            return False
        experiment.status = TrainingLifecycleState(status)
        self.save_experiment(experiment, context=context, action="update_status")
        return True

    def prepare_training_bundle(self, request: PrepareTrainRequest) -> JobBundle:
        experiment = self._require_experiment(request.experiment_id)
        spec = self._build_training_spec(experiment, request.dataset_path)
        actual_bundle_dir = request.bundle_dir or self.bundle_dir_factory(experiment)
        bundle = self.training.render_bundle(spec, bundle_dir=actual_bundle_dir, overwrite=True)
        self._record_bundle_path(experiment, JobKind.TRAIN, bundle)
        experiment.status = TrainingLifecycleState.PREPARED
        self.save_experiment(experiment, context=request.context, action="prepare_training_bundle")
        self._audit_experiment("prepare_training_bundle", request.context, experiment, request=request, result={"bundle_path": str(bundle.path)})
        return bundle

    def submit_training(self, request: SubmitTrainRequest) -> RunHandle:
        experiment = self._require_experiment(request.experiment_id)
        spec = self._build_training_spec(experiment, request.dataset_path)
        actual_bundle_dir = request.bundle_dir or self.bundle_dir_factory(experiment)
        template, execution_request = self._resolve_template(request.template_id, actual_bundle_dir, request.overrides, request.context)
        handle = asyncio.run(
            self.training.launch(
                spec,
                self._require_execution(),
                execution_request=execution_request,
                bundle_dir=actual_bundle_dir,
            )
        )
        bundle = JobBundle(actual_bundle_dir)
        self._record_bundle_path(experiment, JobKind.TRAIN, bundle)
        self._record_run_handle(experiment, JobKind.TRAIN, handle, template_id=template.id, template_snapshot=template.model_dump(mode="json"), execution_request=execution_request.model_dump(mode="json"))
        experiment.status = TrainingLifecycleState.RUNNING
        self.save_experiment(experiment, context=request.context, action="submit_training")
        self._audit_experiment("submit_training", request.context, experiment, request=request, result=handle.model_dump(mode="json"))
        return handle

    def prepare_eval_bundle(self, request: PrepareEvalRequest) -> JobBundle:
        experiment = self._require_experiment(request.experiment_id)
        actual_bundle_dir = request.bundle_dir or self.bundle_dir_factory(experiment)
        bundle = self.eval_builder.build(actual_bundle_dir, job_id=f"{experiment.id}-eval", spec=request.spec, overwrite=True)
        self._record_bundle_path(experiment, JobKind.EVAL, bundle)
        self.save_experiment(experiment, context=request.context, action="prepare_eval_bundle")
        self._audit_experiment("prepare_eval_bundle", request.context, experiment, request=request, result={"bundle_path": str(bundle.path)})
        return bundle

    def submit_eval(self, request: SubmitEvalRequest) -> RunHandle:
        bundle = self.prepare_eval_bundle(
            PrepareEvalRequest(experiment_id=request.experiment_id, spec=request.spec, bundle_dir=request.bundle_dir, context=request.context)
        )
        experiment = self._require_experiment(request.experiment_id)
        template, execution_request = self._resolve_template(request.template_id, str(bundle.path), request.overrides, request.context)
        handle = asyncio.run(self._require_execution().run(execution_request))
        self._record_run_handle(experiment, JobKind.EVAL, handle, template_id=template.id, template_snapshot=template.model_dump(mode="json"), execution_request=execution_request.model_dump(mode="json"))
        self.save_experiment(experiment, context=request.context, action="submit_eval")
        self._audit_experiment("submit_eval", request.context, experiment, request=request, result=handle.model_dump(mode="json"))
        return handle

    def prepare_collect_bundle(self, request: PrepareCollectRequest) -> JobBundle:
        experiment = self._require_experiment(request.experiment_id)
        actual_bundle_dir = request.bundle_dir or self.bundle_dir_factory(experiment)
        bundle = self.collect_builder.build(actual_bundle_dir, job_id=f"{experiment.id}-collect", spec=request.spec, overwrite=True)
        self._record_bundle_path(experiment, JobKind.COLLECT, bundle)
        self.save_experiment(experiment, context=request.context, action="prepare_collect_bundle")
        self._audit_experiment("prepare_collect_bundle", request.context, experiment, request=request, result={"bundle_path": str(bundle.path)})
        return bundle

    def submit_collect(self, request: SubmitCollectRequest) -> RunHandle:
        bundle = self.prepare_collect_bundle(
            PrepareCollectRequest(experiment_id=request.experiment_id, spec=request.spec, bundle_dir=request.bundle_dir, context=request.context)
        )
        experiment = self._require_experiment(request.experiment_id)
        template, execution_request = self._resolve_template(request.template_id, str(bundle.path), request.overrides, request.context)
        handle = asyncio.run(self._require_execution().run(execution_request))
        self._record_run_handle(experiment, JobKind.COLLECT, handle, template_id=template.id, template_snapshot=template.model_dump(mode="json"), execution_request=execution_request.model_dump(mode="json"))
        self.save_experiment(experiment, context=request.context, action="submit_collect")
        self._audit_experiment("submit_collect", request.context, experiment, request=request, result=handle.model_dump(mode="json"))
        return handle

    def refresh_run_status(self, request: RunQuery) -> RunStatus:
        experiment = self._require_experiment(request.experiment_id)
        handle = self._require_run_handle(experiment, request.run_kind)
        status = asyncio.run(self._require_execution().status(RunStatusRequest(handle=handle, context=request.context)))
        self._record_run_status(experiment, request.run_kind, status)
        if request.run_kind == JobKind.TRAIN and status.state.value in {"succeeded", "failed", "terminated"}:
            experiment.status = TrainingLifecycleState(status.state.value)
        self.save_experiment(experiment, context=request.context, action="refresh_run_status")
        self._audit_experiment("refresh_run_status", request.context, experiment, request=request, result=status.model_dump(mode="json"))
        return status

    def collect_run_artifacts(self, request: RunQuery) -> ArtifactManifest:
        experiment = self._require_experiment(request.experiment_id)
        handle = self._require_run_handle(experiment, request.run_kind)
        manifest = asyncio.run(self._require_execution().collect(CollectArtifactsRequest(handle=handle, context=request.context)))
        self._record_manifest(experiment, request.run_kind, manifest)
        self.save_experiment(experiment, context=request.context, action="collect_run_artifacts")
        self._audit_experiment("collect_run_artifacts", request.context, experiment, request=request, result=manifest.model_dump(mode="json"))
        return manifest

    def read_run_logs(self, request: RunLogsQuery) -> str:
        experiment = self._require_experiment(request.experiment_id)
        handle = self._require_run_handle(experiment, request.run_kind)
        output = asyncio.run(self._require_execution().logs(RunLogsRequest(handle=handle, tail=request.tail, context=request.context)))
        self._audit_experiment("read_run_logs", request.context, experiment, request=request, result={"tail": request.tail, "length": len(output)})
        return output

    def terminate_run(self, request: RunQuery) -> None:
        experiment = self._require_experiment(request.experiment_id)
        handle = self._require_run_handle(experiment, request.run_kind)
        asyncio.run(self._require_execution().terminate(TerminateRunRequest(handle=handle, context=request.context)))
        if request.run_kind == JobKind.TRAIN:
            experiment.status = TrainingLifecycleState.TERMINATED
        record = self._ensure_run_record(experiment, request.run_kind)
        record.status = "terminated"
        record.status_detail = "terminated"
        record.status_metadata = {"terminated": True}
        self.save_experiment(experiment, context=request.context, action="terminate_run")
        self._audit_experiment("terminate_run", request.context, experiment, request=request, result={"terminated": True})

    def get_run_handle(self, request: RunQuery) -> RunHandle:
        experiment = self._require_experiment(request.experiment_id)
        return self._require_run_handle(experiment, request.run_kind)

    def record_agent_evaluation(self, experiment_id: str, eval_report, *, context: RequestContext | None = None) -> None:
        experiment = self._require_experiment(experiment_id)
        experiment.status = TrainingLifecycleState.COMPLETED
        experiment.results.agent_eval = AgentEvaluationRecord(
            model_path=eval_report.model_path,
            geo_mean=eval_report.geo_mean,
            environments={env_name: result.mean_score for env_name, result in eval_report.results.items()},
        )
        self.save_experiment(experiment, context=context or RequestContext(), action="record_agent_evaluation")

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

    def _resolve_template(self, template_id: str, bundle_path: str, overrides, context: RequestContext):
        return self.templates.resolve(template_id=template_id, bundle_path=bundle_path, overrides=overrides, context=context)

    def _require_experiment(self, experiment_id: str) -> Experiment:
        experiment = self.load_experiment(experiment_id)
        if experiment is None:
            raise ValueError(f"Experiment not found: {experiment_id}")
        return experiment

    def _require_execution(self) -> ExecutionService:
        if self.execution is None:
            raise ValueError("No execution service configured")
        return self.execution

    def _ensure_run_record(self, experiment: Experiment, run_kind: JobKind) -> RunRecord:
        key = run_record_key(run_kind)
        record = getattr(experiment.results, key)
        if record is None:
            record = RunRecord()
            setattr(experiment.results, key, record)
        return record

    def _require_run_handle(self, experiment: Experiment, run_kind: JobKind) -> RunHandle:
        record = self._ensure_run_record(experiment, run_kind)
        if not record.run_id:
            raise ValueError(f"No {run_kind.value} run recorded for experiment: {experiment.id}")
        return RunHandle(
            runtime_kind=record.runtime_kind,
            run_id=record.run_id,
            target_id=record.target_id,
            submitted_at=float(record.submitted_at or 0.0),
            bundle_path=record.bundle_path,
            metadata=record.metadata or None,
        )

    def _record_bundle_path(self, experiment: Experiment, run_kind: JobKind, bundle: JobBundle) -> None:
        record = self._ensure_run_record(experiment, run_kind)
        record.bundle_path = str(bundle.path)

    def _record_run_handle(
        self,
        experiment: Experiment,
        run_kind: JobKind,
        handle: RunHandle,
        *,
        template_id: str,
        template_snapshot: dict,
        execution_request: dict,
    ) -> None:
        record = self._ensure_run_record(experiment, run_kind)
        record.bundle_path = handle.bundle_path
        record.runtime_kind = handle.runtime_kind
        record.run_id = handle.run_id
        record.target_id = handle.target_id
        record.submitted_at = handle.submitted_at
        record.template_id = template_id
        record.template_snapshot = template_snapshot
        record.execution_request = execution_request
        record.metadata = handle.metadata.model_dump(mode="json") if handle.metadata is not None else {}

    def _record_run_status(self, experiment: Experiment, run_kind: JobKind, status: RunStatus) -> None:
        record = self._ensure_run_record(experiment, run_kind)
        record.status = status.state.value
        record.status_detail = status.detail
        record.status_metadata = dict(status.metadata)

    def _record_manifest(self, experiment: Experiment, run_kind: JobKind, manifest: ArtifactManifest) -> None:
        record = self._ensure_run_record(experiment, run_kind)
        record.logs = dict(manifest.logs)
        record.artifacts = dict(manifest.artifacts)
        record.artifact_metadata = dict(manifest.metadata)

    def _audit_experiment(self, action: str, context: RequestContext, experiment: Experiment, *, request=None, result=None) -> None:
        event = AuditEvent[dict | None, dict | None].build(
            context=context,
            entity_type="experiment",
            entity_id=experiment.id,
            action=action,
            request=request.model_dump(mode="json") if hasattr(request, "model_dump") else request,
            result=result.model_dump(mode="json") if hasattr(result, "model_dump") else result,
        )
        self.audit.write_event(event)
        self.audit.write_snapshot(
            entity_type="experiment",
            entity_id=experiment.id,
            version=str(int(time.time() * 1000)),
            payload=experiment,
            source_event_id=event.event_id,
        )
