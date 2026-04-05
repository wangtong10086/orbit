"""Generic control kernel over experiment state, task plugins, and execution runtimes."""

from __future__ import annotations

import asyncio
import time
import tempfile

from forge.core.audit.writer import AuditEvent, AuditWriter
from forge.core.control.registry import TaskRegistry
from forge.core.contracts.experiments import CreateExperimentRequest, RunLogsQuery, RunQuery, resolve_run_record_key, run_record_key
from forge.core.contracts.execution import (
    ArtifactManifest,
    CollectArtifactsRequest,
    RunHandle,
    RunLogsRequest,
    RunState,
    RunStatus,
    RunStatusRequest,
    TerminateRunRequest,
)
from forge.core.contracts.tasks import TaskSubmission
from forge.core.experiments.models import AgentEvaluationRecord, Experiment, ExperimentResults, RunRecord, TrainingLifecycleState
from forge.core.experiments.store import ExperimentStore
from forge.core.execution.bundle import JobBundle
from forge.core.execution.service import ExecutionService
from forge.core.templates.registry import ExecutionTemplateRegistry
from forge.foundation.schema import RequestContext
from forge.core.control.submission import normalize_submission


class CoreControlService:
    def __init__(
        self,
        experiments: ExperimentStore | None = None,
        execution: ExecutionService | None = None,
        templates: ExecutionTemplateRegistry | None = None,
        task_registry: TaskRegistry | None = None,
        bundle_dir_factory=None,
        audit: AuditWriter | None = None,
    ):
        self.experiments = experiments or ExperimentStore()
        self.execution = execution
        self.templates = templates or ExecutionTemplateRegistry()
        self.task_registry = task_registry or TaskRegistry()
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

    def prepare_task(self, submission: TaskSubmission) -> JobBundle:
        experiment = self._require_experiment(submission.experiment_id)
        plugin = self.task_registry.get(submission.task_type)
        normalized_submission, parsed_request = normalize_submission(plugin, submission)
        issues = plugin.validate_request(parsed_request)
        if issues:
            raise ValueError(f"{submission.task_type} request validation failed: {issues}")
        actual_bundle_dir = normalized_submission.bundle_dir or self.bundle_dir_factory(experiment)
        bundle = plugin.build_bundle(bundle_dir=actual_bundle_dir, submission=normalized_submission)
        self._record_bundle_path(
            experiment,
            plugin.job_kind,
            bundle,
            task_type=normalized_submission.task_type,
            task_request=normalized_submission.task_request,
            run_key=normalized_submission.run_key,
        )
        self.save_experiment(experiment, context=normalized_submission.context, action="prepare_task")
        self._audit_experiment("prepare_task", normalized_submission.context, experiment, request=normalized_submission, result={"bundle_path": str(bundle.path)})
        return bundle

    def submit_task(self, submission: TaskSubmission) -> RunHandle:
        bundle = self.prepare_task(submission)
        experiment = self._require_experiment(submission.experiment_id)
        plugin = self.task_registry.get(submission.task_type)
        normalized_submission, _ = normalize_submission(plugin, submission)
        template, execution_request = self._resolve_template(normalized_submission.template_id, str(bundle.path), normalized_submission.overrides, normalized_submission.context)
        handle = asyncio.run(self._require_execution().run(execution_request))
        self._record_run_handle(
            experiment,
            plugin.job_kind,
            handle,
            task_type=normalized_submission.task_type,
            task_request=normalized_submission.task_request,
            template_id=template.id,
            template_snapshot=template.model_dump(mode="json"),
            execution_request=execution_request.model_dump(mode="json"),
            run_key=normalized_submission.run_key,
        )
        self.save_experiment(experiment, context=normalized_submission.context, action="submit_task")
        self._audit_experiment("submit_task", normalized_submission.context, experiment, request=normalized_submission, result=handle.model_dump(mode="json"))
        return handle

    def refresh_run_status(self, request: RunQuery) -> RunStatus:
        experiment = self._require_experiment(request.experiment_id)
        handle = self._require_run_handle(experiment, request.run_kind, run_key=request.run_key)
        status = asyncio.run(self._require_execution().status(RunStatusRequest(handle=handle, context=request.context)))
        self._record_run_status(experiment, request.run_kind, status, run_key=request.run_key)
        self.save_experiment(experiment, context=request.context, action="refresh_run_status")
        self._audit_experiment("refresh_run_status", request.context, experiment, request=request, result=status.model_dump(mode="json"))
        return status

    def collect_run_artifacts(self, request: RunQuery) -> ArtifactManifest:
        experiment = self._require_experiment(request.experiment_id)
        handle = self._require_run_handle(experiment, request.run_kind, run_key=request.run_key)
        manifest = asyncio.run(self._require_execution().collect(CollectArtifactsRequest(handle=handle, context=request.context)))
        self._record_manifest(experiment, request.run_kind, manifest, run_key=request.run_key)
        record = self._ensure_run_record(experiment, request.run_kind, run_key=request.run_key)
        if record.task_type:
            plugin = self.task_registry.get(record.task_type)
            submission = TaskSubmission(
                experiment_id=request.experiment_id,
                task_type=record.task_type,
                task_request=record.task_request,
                template_id=record.template_id,
                run_key=request.run_key,
                bundle_dir=record.bundle_path,
                context=request.context,
            )
            summary = plugin.summarize_result(
                submission=submission,
                bundle=JobBundle(record.bundle_path),
                status=self._status_from_record(record),
                manifest=manifest,
            )
            record.task_summary = summary
        self.save_experiment(experiment, context=request.context, action="collect_run_artifacts")
        self._audit_experiment("collect_run_artifacts", request.context, experiment, request=request, result=manifest.model_dump(mode="json"))
        return manifest

    def read_run_logs(self, request: RunLogsQuery) -> str:
        experiment = self._require_experiment(request.experiment_id)
        handle = self._require_run_handle(experiment, request.run_kind, run_key=request.run_key)
        output = asyncio.run(self._require_execution().logs(RunLogsRequest(handle=handle, tail=request.tail, context=request.context)))
        self._audit_experiment("read_run_logs", request.context, experiment, request=request, result={"tail": request.tail, "length": len(output)})
        return output

    def terminate_run(self, request: RunQuery) -> None:
        experiment = self._require_experiment(request.experiment_id)
        handle = self._require_run_handle(experiment, request.run_kind, run_key=request.run_key)
        asyncio.run(self._require_execution().terminate(TerminateRunRequest(handle=handle, context=request.context)))
        record = self._ensure_run_record(experiment, request.run_kind, run_key=request.run_key)
        record.status = "terminated"
        record.status_detail = "terminated"
        record.status_metadata = {"terminated": True}
        self.save_experiment(experiment, context=request.context, action="terminate_run")
        self._audit_experiment("terminate_run", request.context, experiment, request=request, result={"terminated": True})

    def record_agent_evaluation(self, experiment_id: str, eval_report, *, context: RequestContext | None = None) -> None:
        experiment = self._require_experiment(experiment_id)
        experiment.status = TrainingLifecycleState.COMPLETED
        experiment.results.agent_eval = AgentEvaluationRecord(
            model_path=eval_report.model_path,
            geo_mean=eval_report.geo_mean,
            environments={env_name: result.mean_score for env_name, result in eval_report.results.items()},
        )
        self.save_experiment(experiment, context=context or RequestContext(), action="record_agent_evaluation")

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

    def _ensure_run_record(self, experiment: Experiment, run_kind, *, run_key: str = "") -> RunRecord:
        key = resolve_run_record_key(run_kind, run_key)
        legacy_key = run_record_key(run_kind)
        if key in experiment.results.task_runs:
            record = experiment.results.task_runs[key]
            if key == legacy_key or not getattr(experiment.results, legacy_key):
                setattr(experiment.results, legacy_key, record)
            return record
        record = None
        if key == legacy_key:
            record = getattr(experiment.results, legacy_key)
        if record is None:
            record = RunRecord()
        experiment.results.task_runs[key] = record
        if key == legacy_key or not getattr(experiment.results, legacy_key):
            setattr(experiment.results, legacy_key, record)
        return record

    def _require_run_handle(self, experiment: Experiment, run_kind, *, run_key: str = "") -> RunHandle:
        record = self._ensure_run_record(experiment, run_kind, run_key=run_key)
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

    def _record_bundle_path(self, experiment: Experiment, run_kind, bundle: JobBundle, *, task_type: str, task_request: dict, run_key: str = "") -> None:
        record = self._ensure_run_record(experiment, run_kind, run_key=run_key)
        record.task_type = task_type
        record.task_request = task_request
        record.bundle_path = str(bundle.path)

    def _record_run_handle(
        self,
        experiment: Experiment,
        run_kind,
        handle: RunHandle,
        *,
        task_type: str,
        task_request: dict,
        template_id: str,
        template_snapshot: dict,
        execution_request: dict,
        run_key: str = "",
    ) -> None:
        record = self._ensure_run_record(experiment, run_kind, run_key=run_key)
        record.task_type = task_type
        record.task_request = task_request
        record.bundle_path = handle.bundle_path
        record.runtime_kind = handle.runtime_kind
        record.run_id = handle.run_id
        record.target_id = handle.target_id
        record.submitted_at = handle.submitted_at
        record.template_id = template_id
        record.template_snapshot = template_snapshot
        record.execution_request = execution_request
        record.metadata = handle.metadata.model_dump(mode="json") if handle.metadata is not None else {}

    def _record_run_status(self, experiment: Experiment, run_kind, status: RunStatus, *, run_key: str = "") -> None:
        record = self._ensure_run_record(experiment, run_kind, run_key=run_key)
        record.status = status.state.value
        record.status_detail = status.detail
        record.status_metadata = dict(status.metadata)

    def _record_manifest(self, experiment: Experiment, run_kind, manifest: ArtifactManifest, *, run_key: str = "") -> None:
        record = self._ensure_run_record(experiment, run_kind, run_key=run_key)
        record.logs = dict(manifest.logs)
        record.artifacts = dict(manifest.artifacts)
        record.artifact_metadata = dict(manifest.metadata)

    def _status_from_record(self, record: RunRecord) -> RunStatus | None:
        if not record.status:
            return None
        return RunStatus(
            runtime_kind=record.runtime_kind,
            run_id=record.run_id,
            state=RunState(record.status),
            detail=record.status_detail,
            metadata=record.status_metadata,
        )

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
