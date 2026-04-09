"""Tests for the execution-plane bundle and worker interfaces."""

from __future__ import annotations

import asyncio
import tarfile

from click.testing import CliRunner
import pytest

from orbit.cli_worker import worker
from orbit.compute.base import GpuInstance
from orbit.config import OrbitConfig
from orbit.tasks.collection.bundle_builder import CollectBundleBuilder
from orbit.tasks.collection.specs import CollectPublishConfig, CollectTaskSpec, NavworldCollectConfig
from orbit.tasks.evaluation.bundle_builder import EvalBundleBuilder
from orbit.tasks.evaluation.specs import EvalTaskSpec
from orbit.tasks.training.bundle_builder import TrainBundleBuilder
from orbit.core.execution.bundle import JobBundle
from orbit.core.contracts.execution import (
    ArtifactManifest,
    CollectArtifactsRequest,
    ExecutionRequest,
    JobKind,
    JobSpec,
    LaunchModeKind,
    LaunchModeSpec,
    LocalDockerRunMetadata,
    PlacementKind,
    PlacementSpec,
    ResourceRequest,
    RunHandle,
    RunLogsRequest,
    RunStatusRequest,
    TargonRentalDockerRunMetadata,
    TargonRentalHostRunMetadata,
)
from orbit.core.execution.backends.local_docker import LocalDockerRuntime
from orbit.core.execution.backends.local_host import LocalHostProcessRuntime
from orbit.core.execution.backends.targon_rental_docker import TargonRentalDockerRuntime
from orbit.core.execution.backends.targon_rental_host import TargonRentalHostProcessRuntime
from orbit.execution.runtimes import (
    create_bundle_archive,
    create_project_snapshot,
)
from orbit.execution.runtimes import _docker_bundle_wrapper, _remote_docker_wrapper, _remote_host_wrapper
from orbit.foundation.audit import AuditWriter
from orbit.training.config import SwiftConfig
from orbit.foundation.contracts import TrainingSpec


def test_train_builder_creates_valid_bundle(tmp_path):
    dataset = tmp_path / "train.jsonl"
    dataset.write_text('{"messages": [{"role": "user", "content": "hi"}]}\n', encoding="utf-8")
    spec = TrainingSpec(
        experiment_id="train-smoke",
        model="Qwen/Qwen2.5-0.5B-Instruct",
        dataset_path=str(dataset),
        train_config=SwiftConfig(model="Qwen/Qwen2.5-0.5B-Instruct", num_train_epochs=1, per_device_train_batch_size=1, output_dir="/tmp/out"),
        environments=("GAME",),
        output_dir="/tmp/out",
    )
    bundle = TrainBundleBuilder().build(str(tmp_path / "bundle"), spec=spec)
    assert bundle.validate() == []
    job = bundle.load_job()
    assert job.kind == JobKind.TRAIN
    assert job.metadata["task_type"] == "train"
    assert (bundle.inputs_dir / "swift_config.yaml").exists()


def test_eval_builder_creates_expected_outputs(tmp_path):
    bundle = EvalBundleBuilder().build(
        str(tmp_path / "bundle"),
        job_id="eval-smoke",
        spec=EvalTaskSpec(model="demo-model", environments=("GAME",), samples=2),
    )
    assert bundle.validate() == []
    job = bundle.load_job()
    assert job.kind == JobKind.EVAL
    assert any(output.relative_path.endswith("eval_summary.json") for output in job.expected_outputs)
    assert "--envs GAME" in bundle.entrypoint_path.read_text(encoding="utf-8")


def test_eval_builder_supports_task_source_mode(tmp_path):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}\n", encoding="utf-8")
    tasks = tmp_path / "test.jsonl"
    tasks.write_text('{"task_id":"g-1","environment":"GAME","prompt":"Return exactly: OK","expected_answer":"OK"}\n', encoding="utf-8")
    bundle = EvalBundleBuilder().build(
        str(tmp_path / "bundle"),
        job_id="eval-task-source",
        spec=EvalTaskSpec(
            model=str(model_dir),
            environments=("GAME",),
            task_source_path=str(tasks),
            max_new_tokens=32,
            temperature=0.0,
        ),
    )
    job = bundle.load_job()
    entrypoint = bundle.entrypoint_path.read_text(encoding="utf-8")
    assert job.kind == JobKind.EVAL
    assert any(input_ref.name == "model" for input_ref in job.inputs)
    assert any(input_ref.name == "task_source" for input_ref in job.inputs)
    assert "orbit.tasks.evaluation.task_source_eval" in entrypoint
    assert "--max-new-tokens 32" in entrypoint


def test_collect_builder_creates_expected_entrypoint(tmp_path):
    bundle = CollectBundleBuilder().build(
        str(tmp_path / "bundle"),
        job_id="collect-smoke",
        spec=CollectTaskSpec(
            env="NAVWORLD",
            collector="navworld-gen",
            output_filename="navworld.jsonl",
            config=NavworldCollectConfig(num=1, model="qwen3-max", phase1=True),
            publish=CollectPublishConfig(hf_repo="user/repo", source="smoke"),
        ),
    )
    assert bundle.validate() == []
    job = bundle.load_job()
    assert job.kind == JobKind.COLLECT
    assert job.metadata["task_type"] == "collect"
    assert "orbit.data.collect_publish" in bundle.entrypoint_path.read_text(encoding="utf-8")


def test_create_project_snapshot_includes_project_tree(tmp_path):
    root = tmp_path / "project"
    (root / "orbit" / "tasks" / "evaluation").mkdir(parents=True)
    (root / "scripts").mkdir(parents=True)
    (root / "orbit" / "__init__.py").write_text("", encoding="utf-8")
    (root / "orbit" / "tasks" / "__init__.py").write_text("", encoding="utf-8")
    (root / "orbit" / "tasks" / "evaluation" / "__init__.py").write_text("", encoding="utf-8")
    (root / "orbit" / "tasks" / "evaluation" / "task_source_eval.py").write_text("print('ok')\n", encoding="utf-8")
    (root / "scripts" / "noop.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (root / "synth_config.json").write_text("{}\n", encoding="utf-8")
    archive = tmp_path / "project.tar.gz"
    config = OrbitConfig(project_root=root, data_dir=root / "data", machines_file=root / "machines.json")

    create_project_snapshot(config, str(archive))

    with tarfile.open(archive, "r:gz") as tar:
        names = set(tar.getnames())
    assert "project/orbit/tasks/evaluation/task_source_eval.py" in names


def test_remote_wrappers_use_orbit_venv():
    docker_wrapper = _docker_bundle_wrapper()
    remote_docker_wrapper = _remote_docker_wrapper(use_hf_staging=False)
    remote_host_wrapper = _remote_host_wrapper()
    for wrapper in (docker_wrapper, remote_docker_wrapper, remote_host_wrapper):
        assert "/opt/orbit-venv/bin/python" in wrapper
        assert "/opt/orbit-venv/bin/activate" in wrapper
        assert "/opt/affine-venv" not in wrapper


def test_worker_run_records_handle_for_follow_up_commands(tmp_path, monkeypatch):
    bundle = JobBundle.create(tmp_path / "bundle", overwrite=True)
    bundle.write_job(JobSpec(job_id="cli-smoke", kind=JobKind.COLLECT))
    bundle.write_text("scripts/entrypoint.sh", "#!/usr/bin/env bash\nexit 0\n", executable=True)
    bundle.record_local_artifacts()

    class _FakeExecutionService:
        def __init__(self, config):
            self.config = config

        async def run(self, request):
            return RunHandle(runtime_kind="fake", run_id="run-123", target_id="local", bundle_path=request.bundle_path)

        async def collect(self, request):
            return ArtifactManifest(logs={"stdout.log": "artifacts/stdout.log"})

    monkeypatch.setattr("orbit.cli_worker.ExecutionService", _FakeExecutionService)
    runner = CliRunner()
    config = OrbitConfig(project_root=tmp_path, data_dir=tmp_path / "data", machines_file=tmp_path / "machines.json")

    result = runner.invoke(worker, ["run", str(bundle.path), "--placement", "local", "--launch-mode", "host_process", "--foreground"], obj={"config": config})
    assert result.exit_code == 0
    assert bundle.load_run_handle().run_id == "run-123"

    collect = runner.invoke(worker, ["collect", str(bundle.path)], obj={"config": config})
    assert collect.exit_code == 0


def test_audit_writer_keeps_absolute_entity_ids_under_audit_root(tmp_path):
    audit = AuditWriter(tmp_path / "audit")
    snapshot_path = audit.write_snapshot(
        entity_type="artifact_manifest",
        entity_id="/tmp/affine-audit-smoke-worker",
        version="1",
        payload={"ok": True},
        source_event_id="test-event",
    )
    assert snapshot_path.exists()
    assert snapshot_path.is_relative_to(tmp_path / "audit")
    assert snapshot_path.parent.name == "%2Ftmp%2Faffine-audit-smoke-worker"


def test_record_local_artifacts_includes_runtime_log(tmp_path):
    bundle = JobBundle.create(tmp_path / "bundle", overwrite=True)
    bundle.write_job(JobSpec(job_id="runtime-log-smoke", kind=JobKind.COLLECT))
    bundle.append_runtime_log("runtime event")
    manifest = bundle.record_local_artifacts()
    assert manifest.logs["runtime.log"] == "runtime/runtime.log"


def test_local_host_runtime_writes_runtime_log(tmp_path):
    bundle = JobBundle.create(tmp_path / "bundle", overwrite=True)
    bundle.write_job(JobSpec(job_id="host-runtime-log", kind=JobKind.COLLECT))
    bundle.write_text(
        "scripts/entrypoint.sh",
        "#!/usr/bin/env bash\nmkdir -p \"$BUNDLE_ROOT/artifacts\"\nprintf 'ok\\n' > \"$BUNDLE_ROOT/artifacts/stdout.log\"\n",
        executable=True,
    )
    runtime = LocalHostProcessRuntime(
        OrbitConfig(project_root=tmp_path, data_dir=tmp_path / "data", machines_file=tmp_path / "machines.json")
    )
    handle = asyncio.run(
        runtime.run(
            ExecutionRequest(
                bundle_path=str(bundle.path),
                placement=PlacementSpec(kind=PlacementKind.LOCAL),
                launch_mode=LaunchModeSpec(kind=LaunchModeKind.HOST_PROCESS, detach=False),
            )
        )
    )
    asyncio.run(runtime.status(RunStatusRequest(handle=handle)))
    manifest = asyncio.run(runtime.collect(CollectArtifactsRequest(handle=handle)))
    runtime_log = bundle.runtime_log_path.read_text(encoding="utf-8")
    assert "run start placement=local launch_mode=host_process" in runtime_log
    assert "status resolved_from=result state=succeeded" in runtime_log
    assert "collect run_id=foreground" in runtime_log
    assert manifest.logs["runtime.log"] == "runtime/runtime.log"


def test_local_host_runtime_runs_foreground_bundle(tmp_path):
    bundle = JobBundle.create(tmp_path / "bundle", overwrite=True)
    bundle.write_job(JobSpec(job_id="host-smoke", kind=JobKind.COLLECT))
    bundle.write_text("scripts/entrypoint.sh", "#!/usr/bin/env bash\nmkdir -p \"$BUNDLE_ROOT/artifacts\"\necho ok > \"$BUNDLE_ROOT/artifacts/stdout.log\"\n", executable=True)
    runtime = LocalHostProcessRuntime(OrbitConfig(project_root=tmp_path, data_dir=tmp_path / "data", machines_file=tmp_path / "machines.json"))
    handle = asyncio.run(
        runtime.run(
            ExecutionRequest(
                bundle_path=str(bundle.path),
                placement=PlacementSpec(kind=PlacementKind.LOCAL),
                launch_mode=LaunchModeSpec(kind=LaunchModeKind.HOST_PROCESS, detach=False),
            )
        )
    )
    status = asyncio.run(runtime.status(RunStatusRequest(handle=handle)))
    assert handle.runtime_kind == "local_host_process"
    assert status.state.value == "succeeded"


def test_local_docker_runtime_logs_fall_back_to_local_artifacts(tmp_path, monkeypatch):
    bundle = JobBundle.create(tmp_path / "bundle", overwrite=True)
    bundle.write_job(JobSpec(job_id="runtime-smoke", kind=JobKind.COLLECT))
    bundle.write_text("scripts/entrypoint.sh", "#!/usr/bin/env bash\nexit 0\n", executable=True)
    (bundle.artifacts_dir / "stdout.log").write_text("hello\nworld\n", encoding="utf-8")
    (bundle.artifacts_dir / "stderr.log").write_text("", encoding="utf-8")

    class Result:
        returncode = 1
        stdout = ""
        stderr = "no such container"

    monkeypatch.setattr("orbit.execution.runtimes.subprocess.run", lambda *args, **kwargs: Result())
    runtime = LocalDockerRuntime(OrbitConfig(project_root=tmp_path, data_dir=tmp_path / "data", machines_file=tmp_path / "machines.json"))
    text = asyncio.run(
        runtime.logs(
            RunLogsRequest(
                handle=RunHandle(
                    runtime_kind="local_docker_image",
                    run_id="missing",
                    target_id="local",
                    bundle_path=str(bundle.path),
                    metadata=LocalDockerRunMetadata(container_name="missing", image="demo", detach=True),
                )
            )
        )
    )
    assert "hello" in text
    assert "world" in text


def test_targon_runtime_requires_rental_target(tmp_path):
    runtime = TargonRentalDockerRuntime(OrbitConfig(project_root=tmp_path, data_dir=tmp_path / "data", machines_file=tmp_path / "machines.json"))
    bundle = JobBundle.create(tmp_path / "bundle", overwrite=True)
    bundle.write_job(JobSpec(job_id="runtime-smoke", kind=JobKind.COLLECT))
    bundle.write_text("scripts/entrypoint.sh", "#!/usr/bin/env bash\nexit 0\n", executable=True)
    with pytest.raises(ValueError, match="requires --target"):
        asyncio.run(
            runtime.run(
                ExecutionRequest(
                    bundle_path=str(bundle.path),
                    placement=PlacementSpec(kind=PlacementKind.TARGON_RENTAL, target=""),
                    launch_mode=LaunchModeSpec(kind=LaunchModeKind.DOCKER_IMAGE, image="demo"),
                )
            )
        )


def test_targon_runtime_uses_hf_staging_instead_of_ssh_upload(tmp_path, monkeypatch):
    bundle = JobBundle.create(tmp_path / "bundle", overwrite=True)
    bundle.write_job(JobSpec(job_id="runtime-smoke", kind=JobKind.COLLECT))
    bundle.write_text("scripts/entrypoint.sh", "#!/usr/bin/env bash\nexit 0\n", executable=True)

    machines = tmp_path / "machines.json"
    machines.write_text('{"machines":[{"name":"r1","host":"ssh.example.com","port":22,"user":"root"}]}', encoding="utf-8")
    runtime = TargonRentalDockerRuntime(
        OrbitConfig(
            project_root=tmp_path,
            data_dir=tmp_path / "data",
            machines_file=machines,
            hf_token="token",
            hf_runtime_repo="user/runtime-stage",
        )
    )

    async def fake_resolve_target(target):
        return GpuInstance(id="r1", backend="ssh", gpu_type="H200", status="ready", host="ssh.example.com", port=22, user="root", metadata={})

    calls = {"uploads": [], "execs": []}

    async def fake_exec(instance, command, timeout=0):
        calls["execs"].append((command, timeout))
        return 0, "container-id", ""

    async def fail_upload(*args, **kwargs):
        raise AssertionError("SSH upload should not be used for Targon rental staging")

    monkeypatch.setattr(runtime, "_resolve_target", fake_resolve_target)
    monkeypatch.setattr(runtime.backend, "exec", fake_exec)
    monkeypatch.setattr(runtime.backend, "upload", fail_upload)

    project_tgz = tmp_path / "project.tar.gz"
    project_tgz.write_bytes(b"project")
    bundle_tgz = tmp_path / "bundle.tar.gz"
    bundle_tgz.write_bytes(b"bundle")
    monkeypatch.setattr("orbit.execution.runtimes.create_project_snapshot", lambda *args, **kwargs: str(project_tgz))
    monkeypatch.setattr("orbit.execution.runtimes.create_bundle_archive", lambda *args, **kwargs: str(bundle_tgz))
    monkeypatch.setattr(
        "orbit.execution.runtimes._upload_runtime_archive",
        lambda local_path, repo_id, path_in_repo, token: calls["uploads"].append((local_path, repo_id, path_in_repo, token)),
    )

    handle = asyncio.run(
        runtime.run(
            ExecutionRequest(
                bundle_path=str(bundle.path),
                placement=PlacementSpec(kind=PlacementKind.TARGON_RENTAL, target="r1"),
                launch_mode=LaunchModeSpec(kind=LaunchModeKind.DOCKER_IMAGE, image="demo"),
                resources=ResourceRequest(gpu_count=8),
            )
        )
    )

    assert len(calls["uploads"]) == 2
    assert all(upload[1] == "user/runtime-stage" for upload in calls["uploads"])
    assert any("--ipc=host" in command for command, _ in calls["execs"])
    assert any("--entrypoint bash" in command for command, _ in calls["execs"])
    assert any("AFFINE_HF_STAGING_REPO=user/runtime-stage" in command for command, _ in calls["execs"])
    assert handle.metadata is not None
    assert handle.metadata.runtime_name == "targon_rental_docker_image"


def test_targon_runtime_logs_fall_back_to_bundle_artifacts(tmp_path, monkeypatch):
    bundle = JobBundle.create(tmp_path / "bundle", overwrite=True)
    bundle.write_job(JobSpec(job_id="runtime-smoke", kind=JobKind.COLLECT))
    bundle.write_text("scripts/entrypoint.sh", "#!/usr/bin/env bash\nexit 0\n", executable=True)

    machines = tmp_path / "machines.json"
    machines.write_text('{"machines":[{"name":"r1","host":"ssh.example.com","port":22,"user":"root"}]}', encoding="utf-8")
    runtime = TargonRentalDockerRuntime(OrbitConfig(project_root=tmp_path, data_dir=tmp_path / "data", machines_file=machines))

    async def fake_resolve_target(target):
        return GpuInstance(id="r1", backend="ssh", gpu_type="H200", status="ready", host="ssh.example.com", port=22, user="root", metadata={})

    calls = {"count": 0}

    async def fake_exec(instance, command, timeout=0):
        calls["count"] += 1
        if calls["count"] == 1:
            return 1, "", "Error response from daemon: No such container"
        return 0, "hello\nworld\n", ""

    monkeypatch.setattr(runtime, "_resolve_target", fake_resolve_target)
    monkeypatch.setattr(runtime.backend, "exec", fake_exec)

    text = asyncio.run(
        runtime.logs(
            RunLogsRequest(
                handle=RunHandle(
                    runtime_kind="targon_rental_docker_image",
                    run_id="missing",
                    target_id="r1",
                    bundle_path=str(bundle.path),
                    metadata=TargonRentalDockerRunMetadata(
                        target="r1",
                        host="ssh.example.com",
                        workspace="/root/orbit-execution/runtime-smoke",
                        container_name="missing",
                        image="demo",
                    ),
                )
            )
        )
    )

    assert "hello" in text
    assert "world" in text


def test_targon_host_runtime_uses_ssh_host_process(tmp_path, monkeypatch):
    bundle = JobBundle.create(tmp_path / "bundle", overwrite=True)
    bundle.write_job(JobSpec(job_id="runtime-host-smoke", kind=JobKind.COLLECT))
    bundle.write_text("scripts/entrypoint.sh", "#!/usr/bin/env bash\nexit 0\n", executable=True)

    machines = tmp_path / "machines.json"
    machines.write_text('{"machines":[{"name":"r1","host":"ssh.example.com","port":22,"user":"root"}]}', encoding="utf-8")
    runtime = TargonRentalHostProcessRuntime(
        OrbitConfig(
            project_root=tmp_path,
            data_dir=tmp_path / "data",
            machines_file=machines,
            hf_token="token",
        )
    )

    async def fake_resolve_target(target):
        return GpuInstance(id="r1", backend="ssh", gpu_type="H200", status="ready", host="ssh.example.com", port=22, user="root", metadata={})

    calls = {"uploads": [], "execs": []}

    async def fake_exec(instance, command, timeout=0):
        calls["execs"].append((command, timeout))
        if "nohup bash" in command:
            return 0, "4321\n", ""
        return 0, "", ""

    async def fake_upload(instance, local_path, remote_path):
        calls["uploads"].append((local_path, remote_path))

    monkeypatch.setattr(runtime, "_resolve_target", fake_resolve_target)
    monkeypatch.setattr(runtime.backend, "exec", fake_exec)
    monkeypatch.setattr(runtime.backend, "upload", fake_upload)

    project_tgz = tmp_path / "project.tar.gz"
    project_tgz.write_bytes(b"project")
    bundle_tgz = tmp_path / "bundle.tar.gz"
    bundle_tgz.write_bytes(b"bundle")
    monkeypatch.setattr("orbit.execution.runtimes.create_project_snapshot", lambda *args, **kwargs: str(project_tgz))
    monkeypatch.setattr("orbit.execution.runtimes.create_bundle_archive", lambda *args, **kwargs: str(bundle_tgz))

    handle = asyncio.run(
        runtime.run(
            ExecutionRequest(
                bundle_path=str(bundle.path),
                placement=PlacementSpec(kind=PlacementKind.TARGON_RENTAL, target="r1"),
                launch_mode=LaunchModeSpec(kind=LaunchModeKind.HOST_PROCESS, detach=True),
                resources=ResourceRequest(gpu_count=8),
            )
        )
    )

    assert handle.runtime_kind == "targon_rental_host_process"
    assert isinstance(handle.metadata, TargonRentalHostRunMetadata)
    assert handle.metadata.pid == 4321
    assert len(calls["uploads"]) == 3
    assert any("nohup bash" in command for command, _ in calls["execs"])
    assert all("docker run" not in command for command, _ in calls["execs"])


def test_targon_host_runtime_exports_remote_dataset_env(tmp_path, monkeypatch):
    bundle = JobBundle.create(tmp_path / "bundle", overwrite=True)
    bundle.write_job(
        JobSpec(
            job_id="runtime-host-remote-dataset",
            kind=JobKind.TRAIN,
            metadata={
                "dataset_transport": "hf_staging",
                "dataset_hf_repo": "user/runtime-stage",
                "dataset_hf_path": "runtime-datasets/runtime-host-remote-dataset/train.jsonl",
                "dataset_hf_repo_type": "model",
                "dataset_filename": "train.jsonl",
            },
        )
    )
    bundle.write_text("scripts/entrypoint.sh", "#!/usr/bin/env bash\nexit 0\n", executable=True)

    machines = tmp_path / "machines.json"
    machines.write_text('{"machines":[{"name":"r1","host":"ssh.example.com","port":22,"user":"root"}]}', encoding="utf-8")
    runtime = TargonRentalHostProcessRuntime(
        OrbitConfig(
            project_root=tmp_path,
            data_dir=tmp_path / "data",
            machines_file=machines,
            hf_token="token",
        )
    )

    async def fake_resolve_target(target):
        return GpuInstance(id="r1", backend="ssh", gpu_type="H200", status="ready", host="ssh.example.com", port=22, user="root", metadata={})

    calls = {"uploads": [], "execs": []}

    async def fake_exec(instance, command, timeout=0):
        calls["execs"].append((command, timeout))
        if "nohup bash" in command:
            return 0, "4321\n", ""
        return 0, "", ""

    async def fake_upload(instance, local_path, remote_path):
        calls["uploads"].append((local_path, remote_path))

    monkeypatch.setattr(runtime, "_resolve_target", fake_resolve_target)
    monkeypatch.setattr(runtime.backend, "exec", fake_exec)
    monkeypatch.setattr(runtime.backend, "upload", fake_upload)

    project_tgz = tmp_path / "project.tar.gz"
    project_tgz.write_bytes(b"project")
    bundle_tgz = tmp_path / "bundle.tar.gz"
    bundle_tgz.write_bytes(b"bundle")
    monkeypatch.setattr("orbit.execution.runtimes.create_project_snapshot", lambda *args, **kwargs: str(project_tgz))
    monkeypatch.setattr("orbit.execution.runtimes.create_bundle_archive", lambda *args, **kwargs: str(bundle_tgz))

    asyncio.run(
        runtime.run(
            ExecutionRequest(
                bundle_path=str(bundle.path),
                placement=PlacementSpec(kind=PlacementKind.TARGON_RENTAL, target="r1"),
                launch_mode=LaunchModeSpec(kind=LaunchModeKind.HOST_PROCESS, detach=True),
                resources=ResourceRequest(gpu_count=4),
            )
        )
    )

    launch_commands = [command for command, _ in calls["execs"] if "nohup bash" in command]
    assert launch_commands
    assert "AFFINE_HF_DATASET_REPO=user/runtime-stage" in launch_commands[0]
    assert "AFFINE_HF_DATASET_PATH=runtime-datasets/runtime-host-remote-dataset/train.jsonl" in launch_commands[0]
    assert "AFFINE_HF_DATASET_FILENAME=train.jsonl" in launch_commands[0]


def test_targon_host_runtime_status_recovers_result_after_process_exit(tmp_path, monkeypatch):
    bundle = JobBundle.create(tmp_path / "bundle", overwrite=True)
    bundle.write_job(JobSpec(job_id="runtime-host-status-smoke", kind=JobKind.COLLECT))
    bundle.write_text("scripts/entrypoint.sh", "#!/usr/bin/env bash\nexit 0\n", executable=True)

    machines = tmp_path / "machines.json"
    machines.write_text('{"machines":[{"name":"r1","host":"ssh.example.com","port":22,"user":"root"}]}', encoding="utf-8")
    runtime = TargonRentalHostProcessRuntime(
        OrbitConfig(project_root=tmp_path, data_dir=tmp_path / "data", machines_file=machines)
    )

    async def fake_resolve_target(target):
        return GpuInstance(id="r1", backend="ssh", gpu_type="H200", status="ready", host="ssh.example.com", port=22, user="root", metadata={})

    calls = {"result_reads": 0}

    async def fake_exec(instance, command, timeout=0):
        if "result.json" in command:
            calls["result_reads"] += 1
            if calls["result_reads"] == 1:
                return 0, "", ""
            return 0, '{"state":"succeeded","exit_code":0}\n', ""
        if "kill -0" in command:
            return 1, "", ""
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(runtime, "_resolve_target", fake_resolve_target)
    monkeypatch.setattr(runtime.backend, "exec", fake_exec)

    handle = RunHandle(
        runtime_kind="targon_rental_host_process",
        run_id="4321",
        target_id="r1",
        bundle_path=str(bundle.path),
        metadata=TargonRentalHostRunMetadata(
            target="r1",
            host="ssh.example.com",
            workspace="/root/orbit-execution/runtime-host-status-smoke",
            pid=4321,
            detach=True,
            entrypoint="scripts/entrypoint.sh",
        ),
    )
    status = asyncio.run(runtime.status(RunStatusRequest(handle=handle)))
    assert status.state.value == "succeeded"


def test_create_bundle_archive_excludes_runtime_and_stale_artifacts(tmp_path):
    bundle = JobBundle.create(tmp_path / "bundle", overwrite=True)
    bundle.write_job(JobSpec(job_id="archive-smoke", kind=JobKind.COLLECT))
    bundle.write_text("scripts/entrypoint.sh", "#!/usr/bin/env bash\nexit 0\n", executable=True)
    bundle.write_run_handle(RunHandle(runtime_kind="local_docker_image", run_id="old-run", target_id="local"))
    (bundle.artifacts_dir / "stdout.log").write_text("old\n", encoding="utf-8")
    bundle.record_local_artifacts()
    archive_path = tmp_path / "bundle.tar.gz"

    create_bundle_archive(bundle, str(archive_path))

    with tarfile.open(archive_path, "r:gz") as tar:
        names = set(tar.getnames())

    assert "bundle/job.json" in names
    assert "bundle/scripts/entrypoint.sh" in names
    assert "bundle/artifacts/manifest.json" in names
    assert "bundle/runtime/last_run.json" not in names
    assert "bundle/artifacts/stdout.log" not in names


def test_local_docker_runtime_uses_ipc_host_for_multi_gpu(tmp_path, monkeypatch):
    bundle = JobBundle.create(tmp_path / "bundle", overwrite=True)
    bundle.write_job(JobSpec(job_id="docker-entrypoint", kind=JobKind.COLLECT))
    bundle.write_text("scripts/entrypoint.sh", "#!/usr/bin/env bash\nexit 0\n", executable=True)
    bundle.record_local_artifacts()
    calls = {}

    class _Result:
        returncode = 0
        stdout = "container-id\n"
        stderr = ""

    def fake_run(cmd, capture_output=True, text=True):
        calls["cmd"] = cmd
        return _Result()

    monkeypatch.setattr("orbit.execution.runtimes.subprocess.run", fake_run)
    runtime = LocalDockerRuntime(OrbitConfig(project_root=tmp_path, data_dir=tmp_path / "data", machines_file=tmp_path / "machines.json"))
    handle = asyncio.run(
        runtime.run(
            ExecutionRequest(
                bundle_path=str(bundle.path),
                placement=PlacementSpec(kind=PlacementKind.LOCAL),
                launch_mode=LaunchModeSpec(kind=LaunchModeKind.DOCKER_IMAGE, image="demo", detach=True),
                resources=ResourceRequest(gpu_count=8),
            )
        )
    )
    assert handle.runtime_kind == "local_docker_image"
    assert "--ipc=host" in calls["cmd"]
    assert "--entrypoint" in calls["cmd"]
    assert "bash" in calls["cmd"]
