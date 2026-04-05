"""Tests for config-driven training launch workflow."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge.config import ForgeConfig
from forge.core.control.service import CoreControlService
from forge.core.experiments import ExperimentStore
from forge.core.templates.registry import ExecutionTemplateRegistry
from forge.core.contracts.execution import (
    CollectArtifactsRequest,
    ExecutionRequest,
    RunHandle,
    RunLogsRequest,
    RunState,
    RunStatus,
    RunStatusRequest,
    TerminateRunRequest,
)
from forge.tasks import build_default_task_registry
from forge.tasks.training.launcher import launch_training_from_path


class _FakeExecution:
    async def run(self, request: ExecutionRequest):
        return RunHandle(
            runtime_kind="fake",
            run_id="run-001",
            target_id=request.placement.target or request.placement.kind.value,
            bundle_path=request.bundle_path,
        )

    async def status(self, request: RunStatusRequest):
        return RunStatus(runtime_kind="fake", run_id=request.handle.run_id, state=RunState.RUNNING)

    async def logs(self, request: RunLogsRequest):
        return "ok\n"

    async def collect(self, request: CollectArtifactsRequest):
        raise AssertionError("collect should not run during launch smoke")

    async def terminate(self, request: TerminateRunRequest):
        return None


def _plane(tmp_path: Path) -> CoreControlService:
    return CoreControlService(
        experiments=ExperimentStore(str(tmp_path / "experiments")),
        execution=_FakeExecution(),
        templates=ExecutionTemplateRegistry(),
        task_registry=build_default_task_registry(),
    )


def test_launch_training_from_local_file_config_creates_experiment_and_submit(tmp_path, monkeypatch):
    dataset = tmp_path / "train.jsonl"
    dataset.write_text('{"messages":[{"role":"user","content":"hi"},{"role":"assistant","content":"hello"}]}\n', encoding="utf-8")
    config_path = tmp_path / "launch.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "kind": "training_launch",
                "experiment": {
                    "id": "v-launch-local",
                    "variable": "launch smoke",
                    "hypothesis": "config launcher reaches control submit",
                    "notes": "local launch smoke",
                },
                "dataset": {
                    "kind": "local_file",
                    "label": "SMOKE",
                    "path": str(dataset),
                },
                "training": {
                    "model": "Qwen/Qwen2.5-0.5B-Instruct",
                    "learning_rate": 1e-4,
                    "lora_rank": 8,
                    "max_length": 512,
                    "num_train_epochs": 1,
                    "output_dir": "/tmp/checkpoints",
                },
                "execution": {
                    "template_id": "local-host",
                    "bundle_dir": str(tmp_path / "bundle"),
                    "detach": True,
                    "resources": {"gpu_type": "unknown", "gpu_count": 0, "cpu_count": 0, "memory_gb": 0},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("WANDB_API_KEY", "wandb-token")

    result = launch_training_from_path(_plane(tmp_path), str(config_path), forge_config=ForgeConfig())

    assert result["experiment_id"] == "v-launch-local"
    assert result["run_handle"]["run_id"] == "run-001"
    assert Path(result["dataset_path"]) == dataset

    reloaded = _plane(tmp_path).load_experiment("v-launch-local")
    assert reloaded is not None
    assert reloaded.train_config["use_hf"] is True
    assert reloaded.train_config["report_to"] == "wandb"
    assert reloaded.train_config["wandb_project"] == "affine-forge"
    assert reloaded.train_config["wandb_run_name"] == "v-launch-local"
    assert reloaded.results.training_run is not None
    assert reloaded.results.training_run.task_type == "training"
    assert reloaded.results.extra["training_launch_config"]["kind"] == "training_launch"
    assert reloaded.results.extra["training_launch_config_path"] == str(config_path)


def test_launch_training_from_hf_config_creates_repo_and_provisions_target(tmp_path, monkeypatch):
    dataset = tmp_path / "downloaded.jsonl"
    dataset.write_text('{"messages":[{"role":"user","content":"x"},{"role":"assistant","content":"y"}]}\n', encoding="utf-8")
    config_path = tmp_path / "launch-hf.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "kind": "training_launch",
                "required_env": ["HF_TOKEN", "TARGON_API_KEY", "TARGON_PROJECT_ID", "TARGON_SSH_KEY_UID"],
                "experiment": {
                    "id": "v-launch-hf",
                    "variable": "hf launch smoke",
                    "hypothesis": "launcher can provision a Targon target",
                },
                "dataset": {
                    "kind": "hf_dataset_file",
                    "label": "SWE-INFINITE",
                    "repo_id": "monokoco/affine-sft-data",
                    "filename": "swe_infinite_v2.jsonl",
                },
                "training": {
                    "model": "Qwen/Qwen2.5-0.5B-Instruct",
                    "learning_rate": 1e-4,
                    "lora_rank": 8,
                    "max_length": 512,
                    "num_train_epochs": 1,
                    "output_dir": "/tmp/checkpoints",
                },
                "publish": {
                    "push_to_hub": True,
                    "hub_model_id": "alice/test-model",
                    "create_repo": True,
                    "private": True,
                },
                "execution": {
                    "template_id": "targon-rental-host",
                    "bundle_dir": str(tmp_path / "bundle"),
                    "detach": True,
                    "resources": {"gpu_type": "NVIDIA-H200", "gpu_count": 1, "cpu_count": 0, "memory_gb": 0},
                    "target": {
                        "kind": "provision_targon_ssh_rental",
                        "workload_name": "affine-launch-smoke",
                        "machine_name": "affine-launch-smoke-h200",
                        "resource": "h200-small",
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("HF_TOKEN", "hf-token")
    monkeypatch.setenv("TARGON_API_KEY", "targon-token")
    monkeypatch.setenv("TARGON_PROJECT_ID", "prj-123")
    monkeypatch.setenv("TARGON_SSH_KEY_UID", "key-123")
    monkeypatch.setenv("WANDB_API_KEY", "wandb-token")

    created_repo = {}

    class _FakeHfApi:
        def __init__(self, token=None):
            created_repo["token"] = token

        def create_repo(self, repo_id, repo_type="model", private=True, exist_ok=True):
            created_repo.update(
                {
                    "repo_id": repo_id,
                    "repo_type": repo_type,
                    "private": private,
                    "exist_ok": exist_ok,
                }
            )

    monkeypatch.setattr("huggingface_hub.HfApi", _FakeHfApi)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", lambda **_: str(dataset))

    provision_calls = {}

    def _fake_provision(*args, **kwargs):
        provision_calls.update(kwargs)
        return {
            "create": {"uid": "wrk-123"},
            "deploy": {"status": "queued"},
            "registered_machine": {"id": "affine-launch-smoke-h200", "host": "ssh.example.com", "port": 22, "user": "root"},
        }

    monkeypatch.setattr("forge.tasks.training.launcher.provision_targon_rental_ssh", _fake_provision)

    result = launch_training_from_path(
        _plane(tmp_path),
        str(config_path),
        forge_config=ForgeConfig(
            hf_token="hf-token",
            targon_api_key="targon-token",
            targon_project_id="prj-123",
            targon_ssh_key_uid="key-123",
        ),
    )

    assert result["target"] == "affine-launch-smoke-h200"
    assert result["provision"]["registered_machine"]["id"] == "affine-launch-smoke-h200"
    assert created_repo["repo_id"] == "alice/test-model"
    assert created_repo["repo_type"] == "model"
    assert provision_calls["name"] == "affine-launch-smoke"
    assert provision_calls["machine_name"] == "affine-launch-smoke-h200"

    reloaded = _plane(tmp_path).load_experiment("v-launch-hf")
    assert reloaded is not None
    assert reloaded.train_config["push_to_hub"] is True
    assert reloaded.train_config["hub_model_id"] == "alice/test-model"
    assert reloaded.train_config["use_hf"] is True
    assert reloaded.train_config["report_to"] == "wandb"
    assert reloaded.train_config["wandb_project"] == "affine-forge"
    assert reloaded.train_config["wandb_run_name"] == "v-launch-hf"
    assert reloaded.data_config["SWE-INFINITE"]["source"] == "hf_dataset_file"


def test_launch_training_can_disable_default_wandb_requirement(tmp_path):
    dataset = tmp_path / "train.jsonl"
    dataset.write_text('{"messages":[{"role":"user","content":"hi"},{"role":"assistant","content":"hello"}]}\n', encoding="utf-8")
    config_path = tmp_path / "launch-no-wandb.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "kind": "training_launch",
                "experiment": {
                    "id": "v-launch-no-wandb",
                    "variable": "launch smoke no wandb",
                    "hypothesis": "explicit report_to=none disables wandb env requirement",
                },
                "dataset": {
                    "kind": "local_file",
                    "label": "SMOKE",
                    "path": str(dataset),
                },
                "training": {
                    "model": "Qwen/Qwen2.5-0.5B-Instruct",
                    "learning_rate": 1e-4,
                    "lora_rank": 8,
                    "max_length": 512,
                    "num_train_epochs": 1,
                    "output_dir": "/tmp/checkpoints",
                    "report_to": "none",
                },
                "execution": {
                    "template_id": "local-host",
                    "bundle_dir": str(tmp_path / "bundle"),
                    "detach": True,
                    "resources": {"gpu_type": "unknown", "gpu_count": 0, "cpu_count": 0, "memory_gb": 0},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = launch_training_from_path(_plane(tmp_path), str(config_path), forge_config=ForgeConfig())

    assert result["experiment_id"] == "v-launch-no-wandb"
    reloaded = _plane(tmp_path).load_experiment("v-launch-no-wandb")
    assert reloaded is not None
    assert reloaded.train_config["report_to"] == "none"


def test_launch_training_uses_dotenv_for_default_required_env(tmp_path, monkeypatch):
    dataset = tmp_path / "train.jsonl"
    dataset.write_text('{"messages":[{"role":"user","content":"hi"},{"role":"assistant","content":"hello"}]}\n', encoding="utf-8")
    config_path = tmp_path / "launch-dotenv.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "kind": "training_launch",
                "required_env": ["HF_TOKEN"],
                "experiment": {
                    "id": "v-launch-dotenv",
                    "variable": "launch smoke dotenv",
                    "hypothesis": "launcher reads required env from dotenv before validation",
                },
                "dataset": {
                    "kind": "local_file",
                    "label": "SMOKE",
                    "path": str(dataset),
                },
                "training": {
                    "model": "Qwen/Qwen2.5-0.5B-Instruct",
                    "learning_rate": 1e-4,
                    "lora_rank": 8,
                    "max_length": 512,
                    "num_train_epochs": 1,
                    "output_dir": "/tmp/checkpoints",
                },
                "execution": {
                    "template_id": "local-host",
                    "bundle_dir": str(tmp_path / "bundle"),
                    "detach": True,
                    "resources": {"gpu_type": "unknown", "gpu_count": 0, "cpu_count": 0, "memory_gb": 0},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("WANDB_API_KEY", raising=False)

    def _fake_load_dotenv():
        os.environ["HF_TOKEN"] = "hf-from-dotenv"
        os.environ["WANDB_API_KEY"] = "wandb-from-dotenv"

    monkeypatch.setattr("forge.tasks.training.launcher.load_dotenv", _fake_load_dotenv)

    result = launch_training_from_path(
        _plane(tmp_path),
        str(config_path),
        forge_config=ForgeConfig(),
    )

    assert result["experiment_id"] == "v-launch-dotenv"
    reloaded = _plane(tmp_path).load_experiment("v-launch-dotenv")
    assert reloaded is not None
    assert reloaded.train_config["wandb_run_name"] == "v-launch-dotenv"
