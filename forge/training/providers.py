"""Explicit execution providers for training workloads."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from forge.compute.base import GpuInstance
from forge.compute.manager import ComputeManager
from forge.config import ForgeConfig
from forge.foundation.contracts import ExecutionProvider, TrainingLaunch, TrainingSpec
from forge.training.config import SwiftConfig
from forge.training.templates import load_template, render_targon_command


@dataclass
class SshExecutionProvider(ExecutionProvider):
    """Launch training on an explicitly selected SSH machine."""

    config: ForgeConfig
    instance: GpuInstance

    @property
    def name(self) -> str:
        return "ssh"

    async def launch_training(self, spec: TrainingSpec) -> TrainingLaunch:
        compute = ComputeManager(self.config)
        backend = compute.get_backend("ssh")

        swift_config = SwiftConfig(**spec.train_config)
        local_yaml = "/tmp/swift_config.yaml"
        Path(local_yaml).write_text(swift_config.to_yaml(spec.dataset_path))
        await backend.upload(self.instance, local_yaml, "/root/scripts/swift_config.yaml")

        swift_cmd = swift_config.swift_command_from_yaml("/root/scripts/swift_config.yaml")
        env_prefix = f"WANDB_API_KEY={self.config.wandb_api_key} " if self.config.wandb_api_key else ""
        command = f"screen -dmS training bash -c '{env_prefix}{swift_cmd} 2>&1 | tee /root/training.log'"
        rc, _, stderr = await backend.exec(self.instance, command, timeout=30)
        if rc != 0:
            raise RuntimeError(f"SSH training launch failed: {stderr}")

        return TrainingLaunch(
            provider_name=self.name,
            run_id=self.instance.id,
            status="submitted",
            metadata={
                "host": self.instance.host or "",
                "port": self.instance.port,
                "user": self.instance.user,
                "key": self.instance.metadata.get("key", ""),
                "command": swift_cmd,
            },
        )

    async def monitor_training(self, launch: TrainingLaunch) -> dict[str, Any]:
        compute = ComputeManager(self.config)
        backend = compute.get_backend("ssh")
        monitor_script = load_template("monitor_ssh.sh")
        rc, stdout, stderr = await backend.exec(self.instance, monitor_script, timeout=30)
        return {
            "provider": self.name,
            "run_id": launch.run_id,
            "returncode": rc,
            "output": stdout,
            "error": stderr,
        }


@dataclass
class _BaseTargonExecutionProvider(ExecutionProvider):
    """Shared low-level Targon launch mechanics with explicit mode classes above it."""

    config: ForgeConfig
    dataset_hf_repo: str
    gpu_type: str = "H200"
    image: str = "pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel"

    def _compute(self) -> ComputeManager:
        return ComputeManager(self.config)

    def _config_filename(self, spec: TrainingSpec) -> str:
        return f"swift_config_{spec.experiment_id}.yaml"

    def _dataset_file(self, spec: TrainingSpec) -> str:
        return os.path.basename(spec.dataset_path)

    def _upload_yaml(self, spec: TrainingSpec) -> str:
        swift_config = SwiftConfig(**spec.train_config)
        yaml_content = swift_config.to_yaml(f"/root/data/{self._dataset_file(spec)}")
        filename = self._config_filename(spec)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as handle:
            handle.write(yaml_content)
            local_yaml = handle.name
        from huggingface_hub import HfApi

        api = HfApi(token=self.config.hf_token)
        api.upload_file(
            path_or_fileobj=local_yaml,
            path_in_repo=filename,
            repo_id=self.dataset_hf_repo,
            repo_type="dataset",
        )
        os.unlink(local_yaml)
        return filename

    def _container_env(self, spec: TrainingSpec, swift_cmd: str, config_filename: str) -> dict[str, str]:
        swift_config = SwiftConfig(**spec.train_config)
        hf_backup_repo = swift_config.hf_backup_repo or self.config.hf_backup_repo
        return {
            "HF_TOKEN": self.config.hf_token,
            "HF_BACKUP_REPO": hf_backup_repo,
            "DATASET_HF_REPO": self.dataset_hf_repo,
            "DATASET_FILE": self._dataset_file(spec),
            "CONFIG_FILE": config_filename,
            "SWIFT_CMD": swift_cmd,
            "NPROC_PER_NODE": str(swift_config.num_gpus),
            "DEBIAN_FRONTEND": "noninteractive",
        }

    async def _deploy(
        self,
        *,
        spec: TrainingSpec,
        swift_cmd: str,
        config_filename: str,
        command: list[str],
        args: list[str],
    ) -> TrainingLaunch:
        compute = self._compute()
        targon = compute.get_backend("targon")
        instance = await targon.provision(
            gpu_type=self.gpu_type,
            name=f"affine-train-{spec.experiment_id.lower()}",
            image=self.image,
            command=command,
            args=args,
            env=self._container_env(spec, swift_cmd, config_filename),
            port=8080,
        )
        return TrainingLaunch(
            provider_name=self.name,
            run_id=instance.id,
            status="submitted",
            metadata={
                "url": instance.url or "",
                "gpu_type": self.gpu_type,
                "image": self.image,
                "dataset_repo": self.dataset_hf_repo,
                "dataset_file": self._dataset_file(spec),
                "config_file": config_filename,
                "command": swift_cmd,
            },
        )

    async def monitor_training(self, launch: TrainingLaunch) -> dict[str, Any]:
        compute = self._compute()
        targon = compute.get_backend("targon")
        instance = GpuInstance(
            id=launch.run_id,
            backend="targon",
            gpu_type=launch.metadata.get("gpu_type", self.gpu_type),
            status=launch.status,
            url=launch.metadata.get("url"),
            metadata=launch.metadata,
        )
        health = await targon.health_check(instance)
        health["provider"] = self.name
        health["run_id"] = launch.run_id
        return health


@dataclass
class TargonBootstrapProvider(_BaseTargonExecutionProvider):
    """Targon provider that bootstraps the runtime from an official base image."""

    image: str = "pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel"

    @property
    def name(self) -> str:
        return "targon-bootstrap"

    async def launch_training(self, spec: TrainingSpec) -> TrainingLaunch:
        config_filename = self._upload_yaml(spec)
        swift_cmd = SwiftConfig(**spec.train_config).swift_command_from_yaml(f"/root/scripts/{config_filename}")
        container_cmd = render_targon_command(
            dataset_hf_repo=self.dataset_hf_repo,
            dataset_file=self._dataset_file(spec),
            swift_cmd=swift_cmd,
            config_file=config_filename,
        )
        return await self._deploy(
            spec=spec,
            swift_cmd=swift_cmd,
            config_filename=config_filename,
            command=["/bin/bash", "-c"],
            args=[container_cmd],
        )


@dataclass
class TargonImageProvider(_BaseTargonExecutionProvider):
    """Targon provider that assumes a prebuilt training image is already prepared."""

    image: str = "wangtong123/affine-forge:latest"

    @property
    def name(self) -> str:
        return "targon-image"

    async def launch_training(self, spec: TrainingSpec) -> TrainingLaunch:
        config_filename = self._upload_yaml(spec)
        swift_cmd = SwiftConfig(**spec.train_config).swift_command_from_yaml(f"/root/scripts/{config_filename}")
        script = load_template("targon_image_train.sh").replace("'", "'\\''")
        return await self._deploy(
            spec=spec,
            swift_cmd=swift_cmd,
            config_filename=config_filename,
            command=["/bin/bash", "-c"],
            args=[f"bash -c '{script}'"],
        )
