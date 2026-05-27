"""Tests for config-driven training launch workflow."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orbit.config import OrbitConfig
from orbit.core.control.service import CoreControlService
from orbit.core.experiments import ExperimentStore
from orbit.core.templates.registry import ExecutionTemplateRegistry
from orbit.core.contracts.execution import (
    CollectArtifactsRequest,
    ExecutionRequest,
    RunHandle,
    RunLogsRequest,
    RunState,
    RunStatus,
    RunStatusRequest,
    TerminateRunRequest,
)
from orbit.core.experiments.models import TrainingLifecycleState
from orbit.tasks import build_default_task_registry
from orbit.tasks.training.launcher import launch_training_from_path


class _FakeExecution:
    last_request: ExecutionRequest | None = None

    async def run(self, request: ExecutionRequest):
        _FakeExecution.last_request = request
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
    _FakeExecution.last_request = None
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

    result = launch_training_from_path(_plane(tmp_path), str(config_path), orbit_config=OrbitConfig())

    assert result["experiment_id"] == "v-launch-local"
    assert result["run_handle"]["run_id"] == "run-001"
    assert Path(result["dataset_path"]) == dataset

    reloaded = _plane(tmp_path).load_experiment("v-launch-local")
    assert reloaded is not None
    assert reloaded.train_config["use_hf"] is True
    assert reloaded.train_config["report_to"] == "wandb"
    assert reloaded.train_config["wandb_project"] == "orbit"
    assert reloaded.train_config["wandb_run_name"] == "v-launch-local"
    assert reloaded.results.training_run is not None
    assert reloaded.results.training_run.task_type == "training"
    assert reloaded.results.extra["training_launch_config_declared"]["kind"] == "training_launch"
    assert reloaded.results.extra["training_launch_config_declared"]["training"] == {
        "model": "Qwen/Qwen2.5-0.5B-Instruct",
        "learning_rate": 1e-4,
        "lora_rank": 8,
        "max_length": 512,
        "num_train_epochs": 1,
        "output_dir": "/tmp/checkpoints",
    }
    assert reloaded.results.extra["training_launch_config_resolved"]["training"]["wandb_run_name"] == "v-launch-local"
    assert reloaded.results.extra["training_launch_config_path"] == str(config_path)
    assert _FakeExecution.last_request is not None
    assert _FakeExecution.last_request.runtime_env["WANDB_PROJECT"] == "orbit"
    assert _FakeExecution.last_request.runtime_env["WANDB_NAME"] == "v-launch-local"
    assert _FakeExecution.last_request.runtime_env["WANDB_MODE"] == "online"
    assert _FakeExecution.last_request.runtime_env["WANDB_DIR"] == "artifacts/wandb"
    assert _FakeExecution.last_request.runtime_env["WANDB__DISABLE_STATS"] == "true"
    assert _FakeExecution.last_request.runtime_env["WANDB__DISABLE_META"] == "true"
    assert _FakeExecution.last_request.runtime_env["WANDB__DISABLE_MACHINE_INFO"] == "true"


def test_launch_training_defaults_wandb_to_offline_without_api_key(tmp_path, monkeypatch):
    _FakeExecution.last_request = None
    dataset = tmp_path / "train.jsonl"
    dataset.write_text('{"messages":[{"role":"user","content":"hi"},{"role":"assistant","content":"hello"}]}\n', encoding="utf-8")
    config_path = tmp_path / "launch-wandb-offline.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "kind": "training_launch",
                "experiment": {
                    "id": "v-launch-wandb-offline",
                    "variable": "launch smoke offline wandb",
                    "hypothesis": "missing WANDB_API_KEY falls back to offline mode",
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
    monkeypatch.delenv("WANDB_API_KEY", raising=False)

    result = launch_training_from_path(_plane(tmp_path), str(config_path), orbit_config=OrbitConfig())

    assert result["experiment_id"] == "v-launch-wandb-offline"
    assert _FakeExecution.last_request is not None
    assert _FakeExecution.last_request.runtime_env["WANDB_MODE"] == "offline"
    assert _FakeExecution.last_request.runtime_env["WANDB_DIR"] == "artifacts/wandb"


def test_launch_training_from_hf_config_creates_repo_and_provisions_target(tmp_path, monkeypatch):
    _FakeExecution.last_request = None
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
                    "repo_id": "monokoco/personal-project-sft-data",
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

    monkeypatch.setattr("orbit.tasks.training.launcher.provision_targon_rental_ssh", _fake_provision)

    result = launch_training_from_path(
        _plane(tmp_path),
        str(config_path),
        orbit_config=OrbitConfig(
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
    assert reloaded.train_config["wandb_project"] == "orbit"
    assert reloaded.train_config["wandb_run_name"] == "v-launch-hf"
    assert reloaded.results.extra["training_launch_config_resolved"]["training"]["hub_model_id"] == "alice/test-model"
    assert reloaded.data_config["SWE-INFINITE"]["source"] == "hf_dataset_file"
    assert _FakeExecution.last_request is not None


def test_launch_training_resolves_rollout_support_paths(tmp_path, monkeypatch):
    _FakeExecution.last_request = None
    dataset = tmp_path / "train.jsonl"
    dataset.write_text(
        '{"messages":[{"role":"user","content":"start"}],"env_config":{"template_name":"company","tier":"lite","seed":0},"episode_id":"ep-000"}\n',
        encoding="utf-8",
    )
    support_dir = tmp_path / "support"
    support_dir.mkdir()
    plugin = support_dir / "memorygym_plugin.py"
    plugin.write_text("print('plugin loaded')\n", encoding="utf-8")
    memorygym_repo = support_dir / "MemoryGym"
    memorygym_repo.mkdir()
    config_path = tmp_path / "launch-rollout.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "kind": "training_launch",
                "experiment": {
                    "id": "v-launch-rollout",
                    "variable": "rollout launch smoke",
                    "hypothesis": "rollout server support paths resolve from config location",
                },
                "dataset": {
                    "kind": "local_file",
                    "label": "MEMORYGYM",
                    "path": str(dataset),
                },
                "training": {
                    "model": "Qwen/Qwen3-8B",
                    "train_type": "rlhf",
                    "rlhf_type": "grpo",
                    "external_plugins": ["support/memorygym_plugin.py"],
                    "report_to": "none",
                    "output_dir": "/tmp/checkpoints",
                },
                "rollout_server": {
                    "enabled": True,
                    "multi_turn_scheduler": "gym_scheduler",
                    "staged_python_packages": ["support/MemoryGym"],
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

    result = launch_training_from_path(_plane(tmp_path), str(config_path), orbit_config=OrbitConfig())

    assert result["experiment_id"] == "v-launch-rollout"
    reloaded = _plane(tmp_path).load_experiment("v-launch-rollout")
    assert reloaded is not None
    assert reloaded.train_config["external_plugins"] == [str(plugin.resolve())]
    assert reloaded.results.extra["training_launch_config_resolved"]["rollout_server"]["staged_python_packages"] == [
        str(memorygym_repo.resolve())
    ]
    assert "WANDB_PROJECT" not in _FakeExecution.last_request.runtime_env
    assert "WANDB_NAME" not in _FakeExecution.last_request.runtime_env


def test_launch_training_resolves_profile_based_memorygym_launch(tmp_path, monkeypatch):
    _FakeExecution.last_request = None
    dataset = tmp_path / "train.jsonl"
    dataset.write_text(
        '{"messages":[{"role":"user","content":"start"}],"env_config":{"template_name":"company","tier":"lite","seed":0},"episode_id":"ep-000"}\n',
        encoding="utf-8",
    )
    config_path = tmp_path / "launch-profile.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "kind": "training_launch",
                "experiment": {
                    "id": "v-launch-profile",
                    "variable": "profile launch smoke",
                    "hypothesis": "launcher resolves profile-based RL config before submit",
                },
                "dataset": {
                    "kind": "local_file",
                    "label": "MEMORYGYM",
                    "path": str(dataset),
                },
                "training": {
                    "model": "Qwen/Qwen3-8B",
                    "train_type": "rlhf",
                    "rlhf_type": "grpo",
                    "profile_id": "memorygym.ms_swift.grpo.server.v1",
                    "profile_overrides": {
                        "max_turns": 64,
                        "vllm_max_model_len": 2048,
                    },
                    "report_to": "none",
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

    result = launch_training_from_path(_plane(tmp_path), str(config_path), orbit_config=OrbitConfig())

    assert result["experiment_id"] == "v-launch-profile"
    reloaded = _plane(tmp_path).load_experiment("v-launch-profile")
    assert reloaded is not None
    assert reloaded.train_config["profile_id"] == "memorygym.ms_swift.grpo.server.v1"
    assert reloaded.train_config["external_plugins"] == [str((Path.cwd() / "scripts" / "memorygym_ms_swift_plugin.py").resolve())]
    resolved = reloaded.results.extra["training_launch_config_resolved"]
    assert resolved["rl_profile_resolved"]["env_pack_id"] == "memorygym"
    assert resolved["rollout_server"]["max_turns"] == 64
    assert resolved["rollout_server"]["staged_python_packages"] == []
    assert resolved["training"]["swift_passthrough"]["gym_env"] == "memorygym_env"


def test_launch_training_stages_large_local_dataset_for_targon(tmp_path, monkeypatch):
    _FakeExecution.last_request = None
    dataset = tmp_path / "large.jsonl"
    dataset.write_text('{"messages":[{"role":"user","content":"x"},{"role":"assistant","content":"y"}]}\n', encoding="utf-8")
    config_path = tmp_path / "launch-large-local.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "kind": "training_launch",
                "required_env": ["HF_TOKEN", "TARGON_API_KEY", "TARGON_PROJECT_ID", "TARGON_SSH_KEY_UID"],
                "experiment": {
                    "id": "v-launch-large-local",
                    "variable": "large local launch smoke",
                    "hypothesis": "launcher stages large local data to HF for remote training",
                },
                "dataset": {
                    "kind": "local_file",
                    "label": "CANONICAL",
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
                    "template_id": "targon-rental-host",
                    "bundle_dir": str(tmp_path / "bundle"),
                    "detach": True,
                    "resources": {"gpu_type": "NVIDIA-H200", "gpu_count": 1, "cpu_count": 0, "memory_gb": 0},
                    "target": {
                        "kind": "provision_targon_ssh_rental",
                        "workload_name": "affine-large-local",
                        "machine_name": "affine-large-local-h200",
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
    monkeypatch.setattr("orbit.tasks.training.launcher._REMOTE_DATASET_STAGE_MIN_BYTES", 1)

    staged = {}

    def _fake_upload_file_to_runtime_repo(*, local_path, repo_id, path_in_repo, token):
        staged.update(
            {
                "local_path": local_path,
                "repo_id": repo_id,
                "path_in_repo": path_in_repo,
                "token": token,
            }
        )

    def _fake_provision(*args, **kwargs):
        return {
            "create": {"uid": "wrk-123"},
            "deploy": {"status": "queued"},
            "registered_machine": {"id": "affine-large-local-h200", "host": "ssh.example.com", "port": 22, "user": "root"},
        }

    monkeypatch.setattr("orbit.tasks.training.launcher._upload_file_to_runtime_repo", _fake_upload_file_to_runtime_repo)
    monkeypatch.setattr("orbit.tasks.training.launcher.provision_targon_rental_ssh", _fake_provision)

    result = launch_training_from_path(
        _plane(tmp_path),
        str(config_path),
        orbit_config=OrbitConfig(
            hf_token="hf-token",
            hf_runtime_repo="user/runtime-stage",
            targon_api_key="targon-token",
            targon_project_id="prj-123",
            targon_ssh_key_uid="key-123",
        ),
    )

    assert result["dataset_staging"]["repo_id"] == "user/runtime-stage"
    assert staged["repo_id"] == "user/runtime-stage"
    assert staged["local_path"] == str(dataset)
    assert staged["path_in_repo"].endswith("/large.jsonl")

    reloaded = _plane(tmp_path).load_experiment("v-launch-large-local")
    assert reloaded is not None
    assert reloaded.results.training_run is not None
    task_request = reloaded.results.training_run.task_request
    assert task_request["dataset_remote_repo"] == "user/runtime-stage"
    assert task_request["dataset_remote_path"].endswith("/large.jsonl")
    assert task_request["dataset_remote_repo_type"] == "model"
    assert task_request["train_config_effective"]["report_to"] == "wandb"


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

    result = launch_training_from_path(_plane(tmp_path), str(config_path), orbit_config=OrbitConfig())

    assert result["experiment_id"] == "v-launch-no-wandb"
    reloaded = _plane(tmp_path).load_experiment("v-launch-no-wandb")
    assert reloaded is not None
    assert reloaded.train_config["report_to"] == "none"


def test_launch_training_supports_native_gkd_config(tmp_path):
    _FakeExecution.last_request = None
    dataset = tmp_path / "gkd.jsonl"
    dataset.write_text('{"messages":[{"role":"user","content":"hi"},{"role":"assistant","content":"hello"}]}\n', encoding="utf-8")
    config_path = tmp_path / "launch-gkd.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "kind": "training_launch",
                "experiment": {
                    "id": "v-launch-gkd",
                    "variable": "native gkd launch",
                    "hypothesis": "training launch passes through native ms-swift gkd",
                },
                "dataset": {
                    "kind": "local_file",
                    "label": "GKD",
                    "path": str(dataset),
                },
                "training": {
                    "model": "Qwen/Qwen3-0.6B",
                    "train_type": "rlhf",
                    "rlhf_type": "gkd",
                    "teacher_model": "Qwen/Qwen3-8B",
                    "max_length": 512,
                    "num_train_epochs": 1,
                    "output_dir": "/tmp/checkpoints",
                    "report_to": "none",
                    "swift_passthrough": {"gkd_logits_topk": 64},
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

    result = launch_training_from_path(_plane(tmp_path), str(config_path), orbit_config=OrbitConfig())

    assert result["experiment_id"] == "v-launch-gkd"
    reloaded = _plane(tmp_path).load_experiment("v-launch-gkd")
    assert reloaded is not None
    assert reloaded.train_config["train_type"] == "rlhf"
    assert reloaded.train_config["rlhf_type"] == "gkd"
    assert reloaded.train_config["teacher_model"] == "Qwen/Qwen3-8B"
    assert reloaded.train_config["swift_passthrough"]["gkd_logits_topk"] == 64
    assert reloaded.results.extra["training_launch_config_declared"]["training"]["teacher_model"] == "Qwen/Qwen3-8B"
    assert reloaded.results.extra["training_launch_requires_vllm"] is True
    assert reloaded.results.extra["training_launch_runtime"] == "native_ms_swift_gkd"
    assert reloaded.results.extra["training_launch_phase"] == "submitted"


def test_launch_training_passes_length_bucketing_into_task_request(tmp_path):
    _FakeExecution.last_request = None
    dataset = tmp_path / "bucketed.jsonl"
    dataset.write_text('{"messages":[{"role":"user","content":"hi"},{"role":"assistant","content":"hello"}]}\n', encoding="utf-8")
    config_path = tmp_path / "launch-bucketed.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "kind": "training_launch",
                "experiment": {
                    "id": "v-launch-bucketed-sft",
                    "variable": "bucketed sft launch",
                    "hypothesis": "launch config passes bucket plan into the training task request",
                },
                "dataset": {
                    "kind": "local_file",
                    "label": "CANONICAL",
                    "path": str(dataset),
                },
                "training": {
                    "model": "Qwen/Qwen3-32B",
                    "train_type": "sft",
                    "tuner_type": "full",
                    "quant_method": None,
                    "quant_bits": None,
                    "max_length": 32768,
                    "output_dir": "/tmp/checkpoints",
                    "report_to": "none",
                },
                "bucketing": {
                    "mode": "auto",
                    "stages": [
                        {
                            "name": "b8",
                            "max_length": 8192,
                            "train_overrides": {"per_device_train_batch_size": 2},
                        },
                        {
                            "name": "b16",
                            "max_length": 16384,
                            "train_overrides": {"per_device_train_batch_size": 1, "gradient_accumulation_steps": 2},
                        },
                        {
                            "name": "b32",
                            "max_length": 32768,
                            "train_overrides": {"per_device_train_batch_size": 1, "gradient_accumulation_steps": 4},
                        },
                    ],
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

    result = launch_training_from_path(_plane(tmp_path), str(config_path), orbit_config=OrbitConfig())

    assert result["experiment_id"] == "v-launch-bucketed-sft"
    reloaded = _plane(tmp_path).load_experiment("v-launch-bucketed-sft")
    assert reloaded is not None
    task_request = reloaded.results.training_run.task_request
    assert task_request["bucketing"]["stages"][0]["name"] == "b8"
    assert task_request["train_config_effective"]["tuner_type"] == "full"
    assert task_request["train_config"]["tuner_type"] == "full"
    assert "quant_method" not in task_request["train_config"]
    assert "lora_rank" not in task_request["train_config"]
    assert task_request["train_config_runtime"]["quant_method"] is None
    assert task_request["bucketing_resolved"][0]["max_length"] == 8192
    assert task_request["bucketing_resolved"][0]["per_device_train_batch_size"] == 2
    assert task_request["bucketing_resolved"][1]["gradient_accumulation_steps"] == 2
    assert task_request["bucketing"]["stages"][1]["train_overrides"]["gradient_accumulation_steps"] == 2
    assert reloaded.results.extra["training_bucket_plan_resolved"][2]["max_length"] == 32768
    assert reloaded.results.extra["training_bucket_plan_resolved"][2]["train_config"]["gradient_accumulation_steps"] == 4
    assert _FakeExecution.last_request is not None


def test_launch_training_persists_effective_config_for_full_training(tmp_path):
    dataset = tmp_path / "train.jsonl"
    dataset.write_text('{"messages":[{"role":"user","content":"hi"},{"role":"assistant","content":"hello"}]}\n', encoding="utf-8")
    config_path = tmp_path / "launch-full.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "kind": "training_launch",
                "experiment": {
                    "id": "v-launch-full",
                    "variable": "full launch",
                    "hypothesis": "effective experiment config drops inactive lora and quant fields",
                },
                "dataset": {
                    "kind": "local_file",
                    "label": "TRAIN",
                    "path": str(dataset),
                },
                "training": {
                    "model": "Qwen/Qwen3-32B",
                    "train_type": "sft",
                    "tuner_type": "full",
                    "quant_method": "bnb",
                    "quant_bits": 4,
                    "max_length": 4096,
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

    launch_training_from_path(_plane(tmp_path), str(config_path), orbit_config=OrbitConfig())

    reloaded = _plane(tmp_path).load_experiment("v-launch-full")
    assert reloaded is not None
    assert reloaded.train_config["tuner_type"] == "full"
    assert "lora_rank" not in reloaded.train_config
    assert "lora_alpha" not in reloaded.train_config
    assert "lora_dropout" not in reloaded.train_config
    assert "target_modules" not in reloaded.train_config
    assert "quant_method" not in reloaded.train_config
    assert "quant_bits" not in reloaded.train_config


def test_launch_training_persists_effective_external_teacher_gkd_config(tmp_path):
    dataset = tmp_path / "gkd.jsonl"
    dataset.write_text('{"messages":[{"role":"user","content":"hi"},{"role":"assistant","content":"hello"}]}\n', encoding="utf-8")
    config_path = tmp_path / "launch-ext-gkd.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "kind": "training_launch",
                "experiment": {
                    "id": "v-launch-ext-gkd",
                    "variable": "external teacher gkd launch",
                    "hypothesis": "effective experiment config drops empty teacher model placeholders",
                },
                "dataset": {
                    "kind": "local_file",
                    "label": "GKD",
                    "path": str(dataset),
                },
                "training": {
                    "model": "Qwen/Qwen3-32B",
                    "train_type": "rlhf",
                    "rlhf_type": "gkd",
                    "teacher_model": "",
                    "max_length": 512,
                    "num_train_epochs": 1,
                    "output_dir": "/tmp/checkpoints",
                    "report_to": "none",
                    "swift_passthrough": {
                        "teacher_model_server": "https://teacher.example/v1",
                        "gkd_logits_topk": 20,
                    },
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

    launch_training_from_path(_plane(tmp_path), str(config_path), orbit_config=OrbitConfig())

    reloaded = _plane(tmp_path).load_experiment("v-launch-ext-gkd")
    assert reloaded is not None
    assert reloaded.train_config["rlhf_type"] == "gkd"
    assert "teacher_model" not in reloaded.train_config
    assert reloaded.train_config["swift_passthrough"]["teacher_model_server"] == "https://teacher.example/v1"
    assert "teacher_model" not in reloaded.results.training_run.task_request["train_config"]


def test_launch_training_persists_offline_topk_gkd_config_without_vllm_requirement(tmp_path):
    dataset = tmp_path / "offline-gkd.jsonl"
    dataset.write_text(
        '{"messages":[{"role":"user","content":"hi"},{"role":"assistant","content":"hello"}],'
        '"response_token_ids":[42],"teacher_topk_indices":[[42,7]],"teacher_topk_logprobs":[[-0.1,-2.0]]}\n',
        encoding="utf-8",
    )
    config_path = tmp_path / "launch-offline-topk-gkd.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "kind": "training_launch",
                "experiment": {
                    "id": "v-launch-offline-topk-gkd",
                    "variable": "offline topk gkd launch",
                    "hypothesis": "effective config preserves offline topk mode without requiring vllm",
                },
                "dataset": {
                    "kind": "local_file",
                    "label": "GKD",
                    "path": str(dataset),
                },
                "training": {
                    "model": "Qwen/Qwen3-0.6B",
                    "train_type": "rlhf",
                    "rlhf_type": "gkd",
                    "teacher_data_mode": "offline_topk",
                    "max_length": 512,
                    "num_train_epochs": 1,
                    "output_dir": "/tmp/checkpoints",
                    "report_to": "none",
                    "swift_passthrough": {"gkd_logits_topk": 20},
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

    launch_training_from_path(_plane(tmp_path), str(config_path), orbit_config=OrbitConfig())

    reloaded = _plane(tmp_path).load_experiment("v-launch-offline-topk-gkd")
    assert reloaded is not None
    assert reloaded.train_config["teacher_data_mode"] == "offline_topk"
    assert "teacher_model" not in reloaded.train_config
    assert reloaded.results.extra["training_launch_requires_vllm"] is False
    assert reloaded.results.training_run.task_request["train_config"]["teacher_data_mode"] == "offline_topk"
    assert reloaded.results.training_run.task_request["train_config_runtime"]["teacher_data_mode"] == "offline_topk"


def test_launch_training_creates_experiment_before_provisioning_target(tmp_path, monkeypatch):
    _FakeExecution.last_request = None
    dataset = tmp_path / "train.jsonl"
    dataset.write_text('{"messages":[{"role":"user","content":"x"},{"role":"assistant","content":"y"}]}\n', encoding="utf-8")
    config_path = tmp_path / "launch-provision-order.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "kind": "training_launch",
                "required_env": ["TARGON_API_KEY", "TARGON_PROJECT_ID", "TARGON_SSH_KEY_UID"],
                "experiment": {
                    "id": "v-launch-provision-order",
                    "variable": "provision order",
                    "hypothesis": "experiment exists before target provisioning starts",
                },
                "dataset": {
                    "kind": "local_file",
                    "label": "SMOKE",
                    "path": str(dataset),
                },
                "training": {
                    "model": "Qwen/Qwen3-0.6B",
                    "max_length": 512,
                    "num_train_epochs": 1,
                    "output_dir": "/tmp/checkpoints",
                    "report_to": "none",
                },
                "execution": {
                    "template_id": "targon-rental-host",
                    "bundle_dir": str(tmp_path / "bundle"),
                    "detach": True,
                    "resources": {"gpu_type": "NVIDIA-H200", "gpu_count": 1, "cpu_count": 0, "memory_gb": 0},
                    "target": {
                        "kind": "provision_targon_ssh_rental",
                        "workload_name": "affine-launch-order",
                        "machine_name": "affine-launch-order-h200",
                        "resource": "h200-small",
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGON_API_KEY", "targon-token")
    monkeypatch.setenv("TARGON_PROJECT_ID", "prj-123")
    monkeypatch.setenv("TARGON_SSH_KEY_UID", "key-123")

    plane = _plane(tmp_path)
    observed = {}

    def _fake_provision(*args, **kwargs):
        experiment = plane.load_experiment("v-launch-provision-order")
        observed["exists"] = experiment is not None
        observed["status"] = experiment.status if experiment is not None else None
        observed["phase"] = experiment.results.extra.get("training_launch_phase") if experiment is not None else None
        return {
            "create": {"uid": "wrk-123"},
            "deploy": {"status": "queued"},
            "registered_machine": {"id": "affine-launch-order-h200", "host": "ssh.example.com", "port": 22, "user": "root"},
        }

    monkeypatch.setattr("orbit.tasks.training.launcher.provision_targon_rental_ssh", _fake_provision)

    result = launch_training_from_path(
        plane,
        str(config_path),
        orbit_config=OrbitConfig(targon_api_key="targon-token", targon_project_id="prj-123", targon_ssh_key_uid="key-123"),
    )

    assert result["experiment_id"] == "v-launch-provision-order"
    assert observed["exists"] is True
    assert observed["status"] == TrainingLifecycleState.PREPARED
    assert observed["phase"] == "provisioning_target"


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

    monkeypatch.setattr("orbit.tasks.training.launcher.load_dotenv", _fake_load_dotenv)

    result = launch_training_from_path(
        _plane(tmp_path),
        str(config_path),
        orbit_config=OrbitConfig(),
    )

    assert result["experiment_id"] == "v-launch-dotenv"
    reloaded = _plane(tmp_path).load_experiment("v-launch-dotenv")
    assert reloaded is not None
    assert reloaded.train_config["wandb_run_name"] == "v-launch-dotenv"
