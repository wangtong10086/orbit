"""Tests for the generic core control kernel and experiment storage."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge.core.control.service import CoreControlService
from forge.core.contracts.experiments import CreateExperimentRequest, RunLogsQuery, RunQuery
from forge.core.contracts.tasks import TaskSubmission
from forge.core.experiments import Experiment, ExperimentStore, RunRecord, TrainingLifecycleState
from forge.core.templates.registry import ExecutionTemplateRegistry
from forge.tasks.collection.specs import CollectTaskSpec, NavworldCollectConfig
from forge.tasks.evaluation.specs import EvalTaskSpec
from forge.tasks import build_default_task_registry
from forge.core.contracts.execution import (
    ArtifactManifest,
    CollectArtifactsRequest,
    ExecutionRequest,
    JobKind,
    RunHandle,
    RunLogsRequest,
    RunState,
    RunStatus,
    RunStatusRequest,
    TerminateRunRequest,
)
from forge.foundation.contracts import TrainingSpec
from forge.training.config import SwiftConfig


class _FakeExecution:
    async def run(self, request: ExecutionRequest):
        return RunHandle(
            runtime_kind="fake",
            run_id="run-001",
            target_id=request.placement.target or request.placement.kind.value,
            bundle_path=request.bundle_path,
        )

    async def status(self, request: RunStatusRequest):
        handle = request.handle
        return RunStatus(runtime_kind=handle.runtime_kind, run_id=handle.run_id, state=RunState.RUNNING, detail="alive")

    async def logs(self, request: RunLogsRequest):
        return "control-log\n"

    async def collect(self, request: CollectArtifactsRequest):
        return ArtifactManifest(logs={"training.log": "artifacts/training.log"}, artifacts={"checkpoints": "artifacts/checkpoints"})

    async def terminate(self, request: TerminateRunRequest):
        return None


def _create_request(**overrides):
    data = {
        "variable": "lr",
        "hypothesis": "lower lr helps",
        "train_config": {
            "model": "Qwen/Qwen3-32B",
            "learning_rate": 1e-4,
            "lora_rank": 64,
            "max_length": 4096,
            "num_train_epochs": 1,
            "output_dir": "/tmp/checkpoints",
        },
        "data_config": {"GAME": {"count": 100}},
    }
    data.update(overrides)
    return CreateExperimentRequest(**data)


class TestCoreControlService:
    def _plane(self, tmp_path):
        return CoreControlService(
            experiments=ExperimentStore(str(tmp_path / "experiments")),
            execution=_FakeExecution(),
            templates=ExecutionTemplateRegistry(),
            task_registry=build_default_task_registry(),
        )

    def _training_submission(self, plane, experiment_id, dataset_path, *, template_id="", bundle_dir=None):
        experiment = plane.load_experiment(experiment_id)
        assert experiment is not None
        config = SwiftConfig.model_validate(experiment.train_config)
        environments = tuple(sorted(experiment.data_config.keys())) if experiment.data_config else tuple()
        return TaskSubmission(
            experiment_id=experiment_id,
            task_type="training",
            task_request=TrainingSpec(
                experiment_id=experiment_id,
                model=config.model,
                dataset_path=dataset_path,
                train_config=config,
                environments=environments,
                output_dir=config.output_dir,
            ).model_dump(mode="json"),
            template_id=template_id,
            bundle_dir=bundle_dir,
        )

    def test_create_and_list(self, tmp_path):
        plane = self._plane(tmp_path)
        created = plane.create_experiment(CreateExperimentRequest(variable="lr", hypothesis="lower lr helps"))
        listed = plane.list_experiments()
        assert created.id
        assert [item.id for item in listed] == [created.id]

    def test_prepare_training_bundle_records_bundle_path(self, tmp_path):
        plane = self._plane(tmp_path)
        dataset = tmp_path / "train.jsonl"
        dataset.write_text('{"messages":[]}\n')
        created = plane.create_experiment(_create_request())
        bundle = plane.prepare_task(
            self._training_submission(plane, created.id, str(dataset), bundle_dir=str(tmp_path / "bundle"))
        )
        reloaded = plane.load_experiment(created.id)
        assert bundle.path.exists()
        assert reloaded is not None
        assert reloaded.results.training_run is not None
        assert reloaded.results.training_run.bundle_path == str(bundle.path)
        assert reloaded.results.training_run.task_type == "training"

    def test_submit_refresh_and_collect_training(self, tmp_path):
        plane = self._plane(tmp_path)
        dataset = tmp_path / "train.jsonl"
        dataset.write_text('{"messages":[]}\n')
        created = plane.create_experiment(_create_request())
        handle = plane.submit_task(
            self._training_submission(
                plane,
                created.id,
                str(dataset),
                template_id="local-host",
                bundle_dir=str(tmp_path / "bundle"),
            )
        )
        status = plane.refresh_run_status(RunQuery(experiment_id=created.id, run_kind=JobKind.TRAIN))
        logs = plane.read_run_logs(RunLogsQuery(experiment_id=created.id, run_kind=JobKind.TRAIN, tail=10))
        manifest = plane.collect_run_artifacts(RunQuery(experiment_id=created.id, run_kind=JobKind.TRAIN))
        reloaded = plane.load_experiment(created.id)
        assert handle.run_id == "run-001"
        assert status.state == RunState.RUNNING
        assert logs == "control-log\n"
        assert manifest.logs["training.log"] == "artifacts/training.log"
        assert reloaded is not None
        assert reloaded.results.training_run is not None
        assert reloaded.results.training_run.template_id == "local-host"
        assert reloaded.results.training_run.task_type == "training"
        assert reloaded.results.training_run.execution_request["placement"]["kind"] == "local"
        assert reloaded.results.training_run.status == "running"
        assert reloaded.results.training_run.task_summary["training_log"] == "artifacts/training.log"

    def test_prepare_eval_and_collect_record_bundle_paths(self, tmp_path):
        plane = self._plane(tmp_path)
        created = plane.create_experiment(_create_request(variable="navworld", hypothesis="more eval and data helps"))
        eval_bundle = plane.prepare_task(
            TaskSubmission(
                experiment_id=created.id,
                task_type="evaluation",
                task_request=EvalTaskSpec(model="Qwen/Qwen2.5-0.5B-Instruct", environments=("GAME",)).model_dump(mode="json"),
                template_id="",
                bundle_dir=str(tmp_path / "bundle-eval"),
            )
        )
        collect_bundle = plane.prepare_task(
            TaskSubmission(
                experiment_id=created.id,
                task_type="collection",
                task_request=CollectTaskSpec(output_filename="navworld_synthetic.jsonl", config=NavworldCollectConfig(num=1)).model_dump(mode="json"),
                template_id="",
                bundle_dir=str(tmp_path / "bundle-collect"),
            )
        )
        reloaded = plane.load_experiment(created.id)
        assert reloaded is not None
        assert eval_bundle.path.exists()
        assert collect_bundle.path.exists()
        assert reloaded.results.evaluation_run is not None
        assert reloaded.results.collect_run is not None

    def test_submit_eval_and_collect_record_run_handles(self, tmp_path):
        plane = self._plane(tmp_path)
        created = plane.create_experiment(_create_request(variable="navworld", hypothesis="more eval and data helps"))
        eval_handle = plane.submit_task(
            TaskSubmission(
                experiment_id=created.id,
                task_type="evaluation",
                task_request=EvalTaskSpec(model="Qwen/Qwen2.5-0.5B-Instruct", environments=("GAME",)).model_dump(mode="json"),
                template_id="local-docker",
                bundle_dir=str(tmp_path / "bundle-eval"),
            )
        )
        collect_handle = plane.submit_task(
            TaskSubmission(
                experiment_id=created.id,
                task_type="collection",
                task_request=CollectTaskSpec(output_filename="navworld_synthetic.jsonl", config=NavworldCollectConfig(num=1)).model_dump(mode="json"),
                template_id="local-docker",
                bundle_dir=str(tmp_path / "bundle-collect"),
            )
        )
        eval_status = plane.refresh_run_status(RunQuery(experiment_id=created.id, run_kind=JobKind.EVAL))
        collect_logs = plane.read_run_logs(RunLogsQuery(experiment_id=created.id, run_kind=JobKind.COLLECT, tail=20))
        reloaded = plane.load_experiment(created.id)
        assert eval_handle.run_id == "run-001"
        assert collect_handle.run_id == "run-001"
        assert eval_status.state == RunState.RUNNING
        assert collect_logs == "control-log\n"
        assert reloaded is not None
        assert reloaded.results.evaluation_run.template_id == "local-docker"
        assert reloaded.results.evaluation_run.task_type == "evaluation"
        assert reloaded.results.collect_run.template_id == "local-docker"
        assert reloaded.results.collect_run.task_type == "collection"

    def test_terminate_run_updates_detail(self, tmp_path):
        plane = self._plane(tmp_path)
        dataset = tmp_path / "train.jsonl"
        dataset.write_text('{"messages":[]}\n')
        created = plane.create_experiment(_create_request())
        plane.submit_task(
            self._training_submission(
                plane,
                created.id,
                str(dataset),
                template_id="local-host",
                bundle_dir=str(tmp_path / "bundle"),
            )
        )
        plane.terminate_run(RunQuery(experiment_id=created.id, run_kind=JobKind.TRAIN))
        reloaded = plane.load_experiment(created.id)
        assert reloaded is not None
        assert reloaded.results.training_run is not None
        assert reloaded.results.training_run.status == "terminated"

    def test_experiment_store_save_merges_stale_run_record_updates(self, tmp_path):
        store = ExperimentStore(str(tmp_path / "experiments"))
        experiment = Experiment(id="v-merge", variable="x", hypothesis="y")
        store.save(experiment)

        stale = store.load("v-merge")
        assert stale is not None

        fresh = store.load("v-merge")
        assert fresh is not None
        fresh.status = TrainingLifecycleState.RUNNING
        fresh.results.collect_run = RunRecord(run_id="run-123", status="succeeded")
        store.save(fresh)

        stale.results.collect_run = RunRecord(bundle_path="/tmp/bundle", artifacts={"artifact": "artifacts/file"})
        store.save(stale)

        reloaded = store.load("v-merge")
        assert reloaded is not None
        assert reloaded.status == TrainingLifecycleState.RUNNING
        assert reloaded.results.collect_run is not None
        assert reloaded.results.collect_run.run_id == "run-123"
        assert reloaded.results.collect_run.status == "succeeded"
        assert reloaded.results.collect_run.bundle_path == "/tmp/bundle"
        assert reloaded.results.collect_run.artifacts["artifact"] == "artifacts/file"
