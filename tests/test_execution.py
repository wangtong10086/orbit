"""Tests for the execution-plane bundle and worker interfaces."""

from __future__ import annotations

import asyncio
import os
import sys

from click.testing import CliRunner
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge.cli_worker import worker
from forge.compute.base import GpuInstance
from forge.config import ForgeConfig
from forge.control.bundles import CollectBundleBuilder, EvalBundleBuilder, TrainBundleBuilder
from forge.control.task_specs import CollectPublishConfig, CollectTaskSpec, EvalTaskSpec, NavworldCollectConfig
from forge.execution.bundle import JobBundle
from forge.execution.contracts import (
    CollectArtifactsRequest,
    ExecutionRequest,
    JobKind,
    JobSpec,
    LaunchModeKind,
    LaunchModeSpec,
    LocalDockerRunMetadata,
    PlacementKind,
    PlacementSpec,
    RunHandle,
    RunLogsRequest,
    RunStatusRequest,
    TargonRentalDockerRunMetadata,
)
from forge.execution.runtimes import LocalDockerRuntime, LocalHostProcessRuntime, TargonRentalDockerRuntime
from forge.training.config import SwiftConfig
from forge.foundation.contracts import TrainingSpec


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
    assert "forge.data.collect_publish" in bundle.entrypoint_path.read_text(encoding="utf-8")


def test_worker_cli_help_lists_execution_commands():
    runner = CliRunner()
    result = runner.invoke(worker, ["--help"])
    assert result.exit_code == 0
    for command in ["run", "status", "logs", "collect", "terminate", "validate-bundle"]:
        assert command in result.output
    assert "render" not in result.output


def test_local_host_runtime_runs_foreground_bundle(tmp_path):
    bundle = JobBundle.create(tmp_path / "bundle", overwrite=True)
    bundle.write_job(JobSpec(job_id="host-smoke", kind=JobKind.COLLECT))
    bundle.write_text("scripts/entrypoint.sh", "#!/usr/bin/env bash\nmkdir -p \"$BUNDLE_ROOT/artifacts\"\necho ok > \"$BUNDLE_ROOT/artifacts/stdout.log\"\n", executable=True)
    runtime = LocalHostProcessRuntime(ForgeConfig(project_root=tmp_path, data_dir=tmp_path / "data", machines_file=tmp_path / "machines.json"))
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

    monkeypatch.setattr("forge.execution.runtimes.subprocess.run", lambda *args, **kwargs: Result())
    runtime = LocalDockerRuntime(ForgeConfig(project_root=tmp_path, data_dir=tmp_path / "data", machines_file=tmp_path / "machines.json"))
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
    runtime = TargonRentalDockerRuntime(ForgeConfig(project_root=tmp_path, data_dir=tmp_path / "data", machines_file=tmp_path / "machines.json"))
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
        ForgeConfig(
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
    monkeypatch.setattr("forge.execution.runtimes.create_project_snapshot", lambda *args, **kwargs: str(project_tgz))
    monkeypatch.setattr("forge.execution.runtimes.create_bundle_archive", lambda *args, **kwargs: str(bundle_tgz))
    monkeypatch.setattr(
        "forge.execution.runtimes._upload_runtime_archive",
        lambda local_path, repo_id, path_in_repo, token: calls["uploads"].append((local_path, repo_id, path_in_repo, token)),
    )

    handle = asyncio.run(
        runtime.run(
            ExecutionRequest(
                bundle_path=str(bundle.path),
                placement=PlacementSpec(kind=PlacementKind.TARGON_RENTAL, target="r1"),
                launch_mode=LaunchModeSpec(kind=LaunchModeKind.DOCKER_IMAGE, image="demo"),
            )
        )
    )

    assert len(calls["uploads"]) == 2
    assert all(upload[1] == "user/runtime-stage" for upload in calls["uploads"])
    assert any("AFFINE_HF_STAGING_REPO=user/runtime-stage" in command for command, _ in calls["execs"])
    assert handle.metadata is not None
    assert handle.metadata.runtime_name == "targon_rental_docker_image"


def test_targon_runtime_logs_fall_back_to_bundle_artifacts(tmp_path, monkeypatch):
    bundle = JobBundle.create(tmp_path / "bundle", overwrite=True)
    bundle.write_job(JobSpec(job_id="runtime-smoke", kind=JobKind.COLLECT))
    bundle.write_text("scripts/entrypoint.sh", "#!/usr/bin/env bash\nexit 0\n", executable=True)

    machines = tmp_path / "machines.json"
    machines.write_text('{"machines":[{"name":"r1","host":"ssh.example.com","port":22,"user":"root"}]}', encoding="utf-8")
    runtime = TargonRentalDockerRuntime(ForgeConfig(project_root=tmp_path, data_dir=tmp_path / "data", machines_file=machines))

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
                        workspace="/root/forge-execution/runtime-smoke",
                        container_name="missing",
                        image="demo",
                    ),
                )
            )
        )
    )

    assert "hello" in text
    assert "world" in text
