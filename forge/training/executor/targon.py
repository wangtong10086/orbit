"""Targon executor — runs ms-swift training on Targon serverless containers.

Wraps forge.compute.targon with training-specific logic:
- Generate swift YAML config and upload to HF
- Launch container with templated entrypoint script
- Monitor and stop instances
"""

from __future__ import annotations

import os
import tempfile

from forge.compute.base import GpuInstance
from forge.config import ForgeConfig
from forge.training.config import SwiftConfig
from forge.training.templates import render_targon_command


class TargonExecutor:
    """Execute ms-swift training on Targon serverless containers."""

    def __init__(self, config: ForgeConfig):
        self.config = config

    async def launch(
        self,
        train_config: SwiftConfig,
        dataset_file: str,
        env_name: str,
        gpu_type: str = "H200",
        dataset_hf_repo: str = "",
    ) -> GpuInstance:
        """Upload swift config to HF and launch Targon container."""
        from forge.compute.manager import ComputeManager

        dataset_hf_repo = dataset_hf_repo or os.environ.get("HF_DATASET_REPO", "")
        if not train_config.hf_backup_repo:
            train_config.hf_backup_repo = self.config.hf_backup_repo or ""

        # Generate YAML config for ms-swift
        yaml_content = train_config.to_yaml(f"/root/data/{dataset_file}")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            local_yaml = f.name

        from huggingface_hub import HfApi
        api = HfApi(token=self.config.hf_token)
        api.upload_file(
            path_or_fileobj=local_yaml,
            path_in_repo="swift_config.yaml",
            repo_id=dataset_hf_repo,
            repo_type="dataset",
        )
        os.unlink(local_yaml)
        print(f"Swift config uploaded to {dataset_hf_repo}/swift_config.yaml")

        # Build container setup + training command from template
        swift_cmd = train_config.swift_command_from_yaml("/root/scripts/swift_config.yaml")
        container_cmd = render_targon_command(
            dataset_hf_repo=dataset_hf_repo,
            dataset_file=dataset_file,
            swift_cmd=swift_cmd,
        )

        compute = ComputeManager(self.config)
        targon = compute.get_backend("targon")
        instance = await targon.provision(
            gpu_type=gpu_type,
            name=f"affine-train-{env_name.lower()}",
            image="pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel",
            command=["/bin/bash", "-c"],
            args=[container_cmd],
            env={
                "HF_TOKEN": self.config.hf_token,
                "HF_BACKUP_REPO": train_config.hf_backup_repo,
                "DATASET_HF_REPO": dataset_hf_repo,
                "DATASET_FILE": dataset_file,
                "SWIFT_CMD": swift_cmd,
                "DEBIAN_FRONTEND": "noninteractive",
            },
            port=8080,
        )

        print(f"Training container deployed on Targon (ms-swift)")
        print(f"  ID: {instance.id}")
        print(f"  URL: {instance.url}")
        print(f"  GPU: {gpu_type}")
        print(f"  Command: {swift_cmd}")
        return instance

    async def monitor(self, instance: GpuInstance) -> dict:
        """Get training status from Targon container."""
        from forge.compute.manager import ComputeManager
        compute = ComputeManager(self.config)
        targon = compute.get_backend("targon")
        return await targon.health_check(instance)

    async def stop(self, instance: GpuInstance) -> None:
        """Terminate Targon container."""
        from forge.compute.manager import ComputeManager
        compute = ComputeManager(self.config)
        targon = compute.get_backend("targon")
        await targon.terminate(instance)
