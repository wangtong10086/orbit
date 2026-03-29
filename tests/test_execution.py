"""Tests for the execution-plane bundle and worker interfaces."""

from __future__ import annotations

import asyncio
import os
import sys

from click.testing import CliRunner

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge.cli_worker import worker
from forge.config import ForgeConfig
from forge.execution.bundle import JobBundle
from forge.execution.contracts import (
    CollectTaskSpec,
    DockerRunMetadata,
    EvalTaskSpec,
    JobKind,
    JobSpec,
    NavworldCollectConfig,
    RunHandle,
    RunLogsRequest,
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
    assert "swift sft --config inputs/swift_config.yaml" in entrypoint
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
    bundle = CollectTaskRenderer().render_navworld(
        str(tmp_path / "bundle"),
        job_id="collect-smoke",
        spec=CollectTaskSpec(
            collector="navworld-gen",
            output_filename="navworld.jsonl",
            config=NavworldCollectConfig(num=1, model="qwen3-max", phase1=True),
        ),
    )

    assert bundle.validate() == []
    job = bundle.load_job()
    assert job.kind.value == "collect"
    entrypoint = bundle.entrypoint_path.read_text(encoding="utf-8")
    assert "from forge.data.navworld_gen import generate_batch" in entrypoint
    assert "PHASE1_TYPES" in entrypoint


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


def test_targon_runtime_script_starts_health_server(tmp_path):
    runtime = TargonRuntime(ForgeConfig(project_root=tmp_path, data_dir=tmp_path / "data", machines_file=tmp_path / "machines.json"))
    script = runtime._runtime_script("repo/name", "project.tar.gz", "bundle.tar.gz", "artifacts.tar.gz", "bootstrap")
    assert "python3 -m http.server 8080" in script
    assert "/tmp/health/index.html" in script
