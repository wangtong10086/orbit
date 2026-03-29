"""Tests for control-plane experiment storage and orchestration."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge.control import ControlPlane, ExperimentStore
from forge.control.contracts import (
    ControlSubmissionTarget,
    CreateExperimentRequest,
    RenderCollectRequest,
    RenderEvalRequest,
    RenderTrainRequest,
    RunLogsQuery,
    RunQuery,
    SubmitCollectRequest,
    SubmitEvalRequest,
    SubmitTrainRequest,
)
from forge.control.experiment import TrainingLifecycleState
from forge.execution.contracts import (
    ArtifactManifest,
    CollectTaskSpec,
    CollectArtifactsRequest,
    DockerTarget,
    EvalTaskSpec,
    JobKind,
    NavworldCollectConfig,
    RunBundleRequest,
    RunHandle,
    RunLogsRequest,
    RunState,
    RunStatus,
    RunStatusRequest,
    TerminateRunRequest,
)


class _FakeRuntime:
    async def run(self, request: RunBundleRequest):
        return RunHandle(
            runtime_kind="fake",
            run_id="run-001",
            target_id=getattr(request.target, "target", "") or "fake-target",
            bundle_path=request.bundle_path,
        )

    async def status(self, request: RunStatusRequest):
        handle = request.handle
        return RunStatus(
            runtime_kind=handle.runtime_kind,
            run_id=handle.run_id,
            state=RunState.RUNNING,
            detail="alive",
        )

    async def logs(self, request: RunLogsRequest):
        return "control-log\n"

    async def collect(self, request: CollectArtifactsRequest):
        return ArtifactManifest(
            logs={"training.log": "artifacts/training.log"},
            artifacts={"checkpoints": "artifacts/checkpoints"},
        )

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


class TestControlPlane:
    def test_create_and_list(self, tmp_path):
        plane = ControlPlane(experiments=ExperimentStore(str(tmp_path)))
        created = plane.create_experiment(CreateExperimentRequest(variable="lr", hypothesis="lower lr helps"))
        listed = plane.list_experiments()
        assert created.id
        assert [item.id for item in listed] == [created.id]

    def test_create_rejects_duplicate_id(self, tmp_path):
        plane = ControlPlane(experiments=ExperimentStore(str(tmp_path)))
        plane.create_experiment(CreateExperimentRequest(experiment_id="v1", variable="lr", hypothesis="one"))
        try:
            plane.create_experiment(CreateExperimentRequest(experiment_id="v1", variable="lr2", hypothesis="two"))
            assert False, "Should reject duplicate ids"
        except ValueError as exc:
            assert "already exists" in str(exc)

    def test_render_training_bundle_records_bundle_path(self, tmp_path):
        plane = ControlPlane(experiments=ExperimentStore(str(tmp_path / "experiments")))
        dataset = tmp_path / "train.jsonl"
        dataset.write_text('{"messages":[]}\n')
        created = plane.create_experiment(_create_request())
        bundle = plane.render_training_bundle(
            RenderTrainRequest(experiment_id=created.id, dataset_path=str(dataset), bundle_dir=str(tmp_path / "bundle"))
        )
        reloaded = plane.load_experiment(created.id)
        assert bundle.path.exists()
        assert reloaded is not None
        assert reloaded.status == TrainingLifecycleState.PREPARED
        assert reloaded.results.training_run is not None
        assert reloaded.results.training_run.bundle_path == str(bundle.path)

    def test_submit_refresh_and_collect_training(self, tmp_path):
        plane = ControlPlane(
            experiments=ExperimentStore(str(tmp_path / "experiments")),
            runtime_factory=lambda runtime_name: _FakeRuntime(),
        )
        dataset = tmp_path / "train.jsonl"
        dataset.write_text('{"messages":[]}\n')
        created = plane.create_experiment(_create_request())
        handle = plane.submit_training(
            SubmitTrainRequest(
                experiment_id=created.id,
                dataset_path=str(dataset),
                submission_target=ControlSubmissionTarget(target=DockerTarget()),
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
        assert reloaded.results.training_run.run_id == "run-001"
        assert reloaded.results.training_run.status == "running"
        assert reloaded.results.training_run.artifacts["checkpoints"] == "artifacts/checkpoints"

    def test_render_eval_and_collect_record_bundle_paths(self, tmp_path):
        plane = ControlPlane(experiments=ExperimentStore(str(tmp_path / "experiments")))
        created = plane.create_experiment(_create_request(variable="navworld", hypothesis="more eval and data helps"))
        eval_bundle = plane.render_eval_bundle(
            RenderEvalRequest(
                experiment_id=created.id,
                spec=EvalTaskSpec(model="Qwen/Qwen2.5-0.5B-Instruct", environments=("GAME",)),
                bundle_dir=str(tmp_path / "bundle-eval"),
            )
        )
        collect_bundle = plane.render_collect_navworld_bundle(
            RenderCollectRequest(
                experiment_id=created.id,
                spec=CollectTaskSpec(output_filename="navworld_synthetic.jsonl", config=NavworldCollectConfig(num=1)),
                bundle_dir=str(tmp_path / "bundle-collect"),
            )
        )
        reloaded = plane.load_experiment(created.id)
        assert reloaded is not None
        assert eval_bundle.path.exists()
        assert collect_bundle.path.exists()
        assert reloaded.results.evaluation_run is not None
        assert reloaded.results.collect_run is not None
        assert reloaded.results.evaluation_run.bundle_path == str(eval_bundle.path)
        assert reloaded.results.collect_run.bundle_path == str(collect_bundle.path)

    def test_submit_eval_and_collect_record_run_handles(self, tmp_path):
        plane = ControlPlane(
            experiments=ExperimentStore(str(tmp_path / "experiments")),
            runtime_factory=lambda runtime_name: _FakeRuntime(),
        )
        created = plane.create_experiment(_create_request(variable="navworld", hypothesis="more eval and data helps"))
        eval_handle = plane.submit_eval(
            SubmitEvalRequest(
                experiment_id=created.id,
                spec=EvalTaskSpec(model="Qwen/Qwen2.5-0.5B-Instruct", environments=("GAME",)),
                submission_target=ControlSubmissionTarget(target=DockerTarget()),
                bundle_dir=str(tmp_path / "bundle-eval"),
            )
        )
        collect_handle = plane.submit_collect_navworld(
            SubmitCollectRequest(
                experiment_id=created.id,
                spec=CollectTaskSpec(output_filename="navworld_synthetic.jsonl", config=NavworldCollectConfig(num=1)),
                submission_target=ControlSubmissionTarget(target=DockerTarget()),
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
        assert reloaded.results.evaluation_run is not None
        assert reloaded.results.collect_run is not None
        assert reloaded.results.evaluation_run.run_id == "run-001"
        assert reloaded.results.collect_run.run_id == "run-001"
        assert reloaded.status == TrainingLifecycleState.DRAFT

    def test_get_run_handle(self, tmp_path):
        plane = ControlPlane(
            experiments=ExperimentStore(str(tmp_path / "experiments")),
            runtime_factory=lambda runtime_name: _FakeRuntime(),
        )
        dataset = tmp_path / "train.jsonl"
        dataset.write_text('{"messages":[]}\n')
        created = plane.create_experiment(_create_request())
        plane.submit_training(
            SubmitTrainRequest(
                experiment_id=created.id,
                dataset_path=str(dataset),
                submission_target=ControlSubmissionTarget(target=DockerTarget()),
                bundle_dir=str(tmp_path / "bundle"),
            )
        )
        handle = plane.get_run_handle(RunQuery(experiment_id=created.id, run_kind=JobKind.TRAIN))
        assert handle.run_id == "run-001"

    def test_terminate_run_updates_detail(self, tmp_path):
        plane = ControlPlane(
            experiments=ExperimentStore(str(tmp_path / "experiments")),
            runtime_factory=lambda runtime_name: _FakeRuntime(),
        )
        dataset = tmp_path / "train.jsonl"
        dataset.write_text('{"messages":[]}\n')
        created = plane.create_experiment(_create_request())
        plane.submit_training(
            SubmitTrainRequest(
                experiment_id=created.id,
                dataset_path=str(dataset),
                submission_target=ControlSubmissionTarget(target=DockerTarget()),
                bundle_dir=str(tmp_path / "bundle"),
            )
        )
        plane.terminate_run(RunQuery(experiment_id=created.id, run_kind=JobKind.TRAIN))
        reloaded = plane.load_experiment(created.id)
        assert reloaded is not None
        assert reloaded.status == TrainingLifecycleState.TERMINATED
        assert reloaded.results.training_run is not None
        assert reloaded.results.training_run.status == "terminated"
        assert reloaded.results.training_run.status_detail == "terminated"
