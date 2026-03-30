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
from forge.execution.bundle import JobBundle
from forge.execution.contracts import (
    CollectPublishConfig,
    CollectTaskSpec,
    DockerRunMetadata,
    EvalTaskSpec,
    JobKind,
    JobSpec,
    NavworldCollectConfig,
    RunBundleRequest,
    RunHandle,
    RunLogsRequest,
    TargonTarget,
)
from forge.execution.renderers import CollectTaskRenderer, EvalTaskRenderer, TrainTaskRenderer
from forge.execution.runtimes import DockerRuntime, TargonRuntime
from forge.training.config import SwiftConfig


def test_train_renderer_creates_valid_bundle(tmp_path):
    dataset = tmp_path / "train.jsonl"
    dataset.write_text('{"messages": [{"role": "user", "content": "hi"}]}\n', encoding="utf-8")

    bundle = TrainTaskRenderer().render(
        str(tmp_path / "bundle"),
        job_id="train-smoke",
        dataset_path=str(dataset),
        config=SwiftConfig(model="Qwen/Qwen2.5-0.5B-Instruct", num_train_epochs=1, per_device_train_batch_size=1),
    )

    assert bundle.validate() == []
    job = bundle.load_job()
    assert job.kind.value == "train"
    assert bundle.job_path.exists()
    assert (bundle.inputs_dir / "swift_config.yaml").exists()
    entrypoint = bundle.entrypoint_path.read_text(encoding="utf-8")
    assert 'swift sft --config "${BUNDLE_ROOT}/inputs/swift_config.yaml"' in entrypoint
    assert "artifacts/training.log" in entrypoint


def test_eval_renderer_creates_expected_outputs(tmp_path):
    bundle = EvalTaskRenderer().render(
        str(tmp_path / "bundle"),
        job_id="eval-smoke",
        spec=EvalTaskSpec(model="demo-model", environments=("GAME",), samples=2),
    )

    assert bundle.validate() == []
    job = bundle.load_job()
    assert job.kind.value == "eval"
    assert any(output.relative_path.endswith("eval_summary.json") for output in job.expected_outputs)
    assert "--envs GAME" in bundle.entrypoint_path.read_text(encoding="utf-8")


def test_collect_renderer_navworld_creates_expected_entrypoint(tmp_path):
    bundle = CollectTaskRenderer().render(
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
    assert job.kind.value == "collect"
    entrypoint = bundle.entrypoint_path.read_text(encoding="utf-8")
    assert "forge.data.collect_publish" in entrypoint
    assert (bundle.inputs_dir / "collect_spec.json").exists()


def test_worker_cli_help_lists_execution_commands():
    runner = CliRunner()
    result = runner.invoke(worker, ["--help"])
    assert result.exit_code == 0
    for command in ["render", "run", "status", "logs", "collect", "terminate", "validate-bundle"]:
        assert command in result.output


def test_worker_render_train_and_validate_bundle(tmp_path):
    dataset = tmp_path / "train.jsonl"
    dataset.write_text('{"messages": [{"role": "user", "content": "hi"}]}\n', encoding="utf-8")
    bundle_dir = tmp_path / "bundle"

    runner = CliRunner()
    render = runner.invoke(
        worker,
        [
            "render",
            "train",
            str(dataset),
            "--bundle-dir",
            str(bundle_dir),
            "--job-id",
            "cli-train",
            "--model",
            "Qwen/Qwen2.5-0.5B-Instruct",
            "--epochs",
            "1",
            "--batch-size",
            "1",
        ],
    )
    assert render.exit_code == 0

    validate = runner.invoke(worker, ["validate-bundle", str(bundle_dir)])
    assert validate.exit_code == 0

    bundle = JobBundle(bundle_dir)
    job = bundle.load_job()
    assert job.job_id == "cli-train"


def test_docker_runtime_logs_fall_back_to_local_artifacts(tmp_path, monkeypatch):
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
    runtime = DockerRuntime(ForgeConfig(project_root=tmp_path, data_dir=tmp_path / "data", machines_file=tmp_path / "machines.json"))
    text = asyncio.run(
        runtime.logs(
            RunLogsRequest(
                handle=RunHandle(
                    runtime_kind="docker",
                    run_id="missing",
                    target_id="missing",
                    bundle_path=str(bundle.path),
                    metadata=DockerRunMetadata(container_name="missing", image="demo", detach=True),
                )
            )
        )
    )
    assert "hello" in text
    assert "world" in text


def test_targon_runtime_requires_rental_target(tmp_path):
    runtime = TargonRuntime(ForgeConfig(project_root=tmp_path, data_dir=tmp_path / "data", machines_file=tmp_path / "machines.json"))
    bundle = JobBundle.create(tmp_path / "bundle", overwrite=True)
    bundle.write_job(JobSpec(job_id="runtime-smoke", kind=JobKind.COLLECT))
    bundle.write_text("scripts/entrypoint.sh", "#!/usr/bin/env bash\nexit 0\n", executable=True)
    with pytest.raises(ValueError, match="requires --target"):
        asyncio.run(runtime.run(RunBundleRequest(bundle_path=str(bundle.path), target=TargonTarget(target="", image="demo"))))


def test_targon_runtime_uses_hf_staging_instead_of_ssh_upload(tmp_path, monkeypatch):
    bundle = JobBundle.create(tmp_path / "bundle", overwrite=True)
    bundle.write_job(JobSpec(job_id="runtime-smoke", kind=JobKind.COLLECT))
    bundle.write_text("scripts/entrypoint.sh", "#!/usr/bin/env bash\nexit 0\n", executable=True)

    machines = tmp_path / "machines.json"
    machines.write_text('{"machines":[{"name":"r1","host":"ssh.example.com","port":22,"user":"root"}]}', encoding="utf-8")
    runtime = TargonRuntime(
        ForgeConfig(
            project_root=tmp_path,
            data_dir=tmp_path / "data",
            machines_file=machines,
            hf_token="token",
            hf_runtime_repo="user/runtime-stage",
        )
    )

    async def fake_resolve_target(target):
        return GpuInstance(
            id="r1",
            backend="ssh",
            gpu_type="H200",
            status="ready",
            host="ssh.example.com",
            port=22,
            user="root",
            metadata={},
        )

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
            RunBundleRequest(
                bundle_path=str(bundle.path),
                target=TargonTarget(target="r1", image="demo"),
            )
        )
    )

    assert len(calls["uploads"]) == 2
    assert all(upload[1] == "user/runtime-stage" for upload in calls["uploads"])
    assert any("AFFINE_HF_STAGING_REPO=user/runtime-stage" in command for command, _ in calls["execs"])
    assert handle.metadata is not None
    assert handle.metadata.runtime_name == "targon"


def test_targon_runtime_falls_back_to_ssh_upload_without_hf_staging(tmp_path, monkeypatch):
    bundle = JobBundle.create(tmp_path / "bundle", overwrite=True)
    bundle.write_job(JobSpec(job_id="runtime-smoke", kind=JobKind.COLLECT))
    bundle.write_text("scripts/entrypoint.sh", "#!/usr/bin/env bash\nexit 0\n", executable=True)

    machines = tmp_path / "machines.json"
    machines.write_text('{"machines":[{"name":"r1","host":"ssh.example.com","port":22,"user":"root"}]}', encoding="utf-8")
    runtime = TargonRuntime(
        ForgeConfig(
            project_root=tmp_path,
            data_dir=tmp_path / "data",
            machines_file=machines,
        )
    )

    async def fake_resolve_target(target):
        return GpuInstance(
            id="r1",
            backend="ssh",
            gpu_type="H200",
            status="ready",
            host="ssh.example.com",
            port=22,
            user="root",
            metadata={},
        )

    calls = {"uploads": [], "execs": []}

    async def fake_exec(instance, command, timeout=0):
        calls["execs"].append((command, timeout))
        return 0, "container-id", ""

    async def fake_upload(instance, local_path, remote_path):
        calls["uploads"].append((local_path, remote_path))

    monkeypatch.setattr(runtime, "_resolve_target", fake_resolve_target)
    monkeypatch.setattr(runtime.backend, "exec", fake_exec)
    monkeypatch.setattr(runtime.backend, "upload", fake_upload)
    monkeypatch.setattr(
        "forge.execution.runtimes._upload_runtime_archive",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("HF staging should not be used when config is absent")),
    )

    project_tgz = tmp_path / "project.tar.gz"
    project_tgz.write_bytes(b"project")
    bundle_tgz = tmp_path / "bundle.tar.gz"
    bundle_tgz.write_bytes(b"bundle")
    monkeypatch.setattr("forge.execution.runtimes.create_project_snapshot", lambda *args, **kwargs: str(project_tgz))
    monkeypatch.setattr("forge.execution.runtimes.create_bundle_archive", lambda *args, **kwargs: str(bundle_tgz))

    handle = asyncio.run(
        runtime.run(
            RunBundleRequest(
                bundle_path=str(bundle.path),
                target=TargonTarget(target="r1", image="demo"),
            )
        )
    )

    assert calls["uploads"] == [
        (str(project_tgz), "/root/forge-execution/runtime-smoke/project.tar.gz"),
        (str(bundle_tgz), "/root/forge-execution/runtime-smoke/bundle.tar.gz"),
    ]
    assert any("-v /root/forge-execution/runtime-smoke:/staging" in command for command, _ in calls["execs"])
    assert handle.metadata is not None
    assert handle.metadata.staging_repo == ""


def test_targon_runtime_foreground_runs_without_detach(tmp_path, monkeypatch):
    bundle = JobBundle.create(tmp_path / "bundle", overwrite=True)
    bundle.write_job(JobSpec(job_id="runtime-smoke", kind=JobKind.COLLECT))
    bundle.write_text("scripts/entrypoint.sh", "#!/usr/bin/env bash\nexit 0\n", executable=True)

    machines = tmp_path / "machines.json"
    machines.write_text('{"machines":[{"name":"r1","host":"ssh.example.com","port":22,"user":"root"}]}', encoding="utf-8")
    runtime = TargonRuntime(
        ForgeConfig(
            project_root=tmp_path,
            data_dir=tmp_path / "data",
            machines_file=machines,
        )
    )

    async def fake_resolve_target(target):
        return GpuInstance(
            id="r1",
            backend="ssh",
            gpu_type="H200",
            status="ready",
            host="ssh.example.com",
            port=22,
            user="root",
            metadata={},
        )

    calls = {"execs": []}

    async def fake_exec(instance, command, timeout=0):
        calls["execs"].append((command, timeout))
        return 0, "container-id", ""

    async def fake_upload(*args, **kwargs):
        return None

    monkeypatch.setattr(runtime, "_resolve_target", fake_resolve_target)
    monkeypatch.setattr(runtime.backend, "exec", fake_exec)
    monkeypatch.setattr(runtime.backend, "upload", fake_upload)
    monkeypatch.setattr("forge.execution.runtimes.create_project_snapshot", lambda *args, **kwargs: str(tmp_path / "project.tar.gz"))
    monkeypatch.setattr("forge.execution.runtimes.create_bundle_archive", lambda *args, **kwargs: str(tmp_path / "bundle.tar.gz"))
    (tmp_path / "project.tar.gz").write_bytes(b"project")
    (tmp_path / "bundle.tar.gz").write_bytes(b"bundle")

    asyncio.run(
        runtime.run(
            RunBundleRequest(
                bundle_path=str(bundle.path),
                target=TargonTarget(target="r1", image="demo", detach=False),
            )
        )
    )

    launch_command = calls["execs"][-1][0]
    assert "docker run --gpus all --name forge-worker-runtime-smoke --rm " in launch_command
    assert "docker run --gpus all --name forge-worker-runtime-smoke -d " not in launch_command
