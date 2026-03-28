"""Training pipeline runner — orchestrates ms-swift training on remote machines."""

import os
import asyncio
from typing import Optional

from forge.config import ForgeConfig
from forge.compute.manager import ComputeManager
from forge.compute.base import GpuInstance
from forge.training.config import SwiftConfig
from forge.training.templates import render_targon_command, load_template


# Alias for backward compatibility
TrainConfig = SwiftConfig


class TrainingRunner:
    """Orchestrates the full training pipeline using ms-swift."""

    def __init__(self, config: ForgeConfig):
        self.config = config
        self.compute = ComputeManager(config)

    async def launch_on_ssh(
        self,
        instance: GpuInstance,
        dataset_path: str,
        train_config: Optional[SwiftConfig] = None,
    ) -> None:
        """Launch ms-swift training on an SSH-accessible instance.

        Uploads a YAML config and runs ``swift sft/rlhf`` on the remote machine.
        ms-swift must be installed on the remote instance.
        """
        tc = train_config or SwiftConfig()

        # Generate and upload YAML config
        yaml_content = tc.to_yaml(dataset_path)
        local_yaml = "/tmp/swift_config.yaml"
        with open(local_yaml, "w") as f:
            f.write(yaml_content)

        be = self.compute.get_backend("ssh")
        await be.upload(instance, local_yaml, "/root/scripts/swift_config.yaml")

        # Build swift command
        swift_cmd = tc.swift_command_from_yaml("/root/scripts/swift_config.yaml")
        env_prefix = ""
        if self.config.wandb_api_key:
            env_prefix = f"WANDB_API_KEY={self.config.wandb_api_key} "
        cmd = f"screen -dmS training bash -c '{env_prefix}{swift_cmd} 2>&1 | tee /root/training.log'"
        rc, stdout, stderr = await be.exec(instance, cmd, timeout=30)

        if rc == 0:
            print(f"Training launched on {instance.host}")
            print(f"  Command: {swift_cmd}")
            print(f"  Monitor: forge train monitor {instance.id}")
        else:
            print(f"Failed to launch: {stderr}")

    async def launch_on_targon(
        self,
        env: str,
        train_config: Optional[SwiftConfig] = None,
        gpu_type: str = "H200",
        dataset_hf_repo: str = os.environ.get("HF_DATASET_REPO", ""),
        dataset_file: Optional[str] = None,
    ) -> GpuInstance:
        """Launch ms-swift training as a Targon serverless container.

        The container installs ms-swift, downloads dataset from HuggingFace,
        and runs ``swift sft/rlhf`` with the generated YAML config.
        """
        tc = train_config or SwiftConfig()
        if not tc.hf_backup_repo:
            tc.hf_backup_repo = self.config.hf_backup_repo or os.environ.get("HF_BACKUP_REPO", "")

        dataset_file = dataset_file or f"{env.lower()}_sft.jsonl"

        # Generate YAML config and upload to HF
        yaml_content = tc.to_yaml(f"/root/data/{dataset_file}")
        import tempfile
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

        # Build swift command and container entrypoint from template
        swift_cmd = tc.swift_command_from_yaml("/root/scripts/swift_config.yaml")
        container_cmd = render_targon_command(
            dataset_hf_repo=dataset_hf_repo,
            dataset_file=dataset_file,
            swift_cmd=swift_cmd,
        )

        targon = self.compute.get_backend("targon")
        container_env = {
            "HF_TOKEN": self.config.hf_token,
            "HF_BACKUP_REPO": tc.hf_backup_repo,
            "DATASET_HF_REPO": dataset_hf_repo,
            "DATASET_FILE": dataset_file,
            "SWIFT_CMD": swift_cmd,
            "NPROC_PER_NODE": str(tc.num_gpus),
            "DEBIAN_FRONTEND": "noninteractive",
        }
        if self.config.wandb_api_key:
            container_env["WANDB_API_KEY"] = self.config.wandb_api_key
        instance = await targon.provision(
            gpu_type=gpu_type,
            name=f"affine-train-{env.lower()}",
            image="pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel",
            command=["/bin/bash", "-c"],
            args=[container_cmd],
            env=container_env,
            port=8080,
        )

        print(f"Training container deployed on Targon (ms-swift)")
        print(f"  ID: {instance.id}")
        print(f"  URL: {instance.url}")
        print(f"  GPU: {gpu_type}")
        print(f"  Command: {swift_cmd}")
        print(f"  Dataset: {dataset_hf_repo}/{dataset_file}")

        return instance

    async def monitor(self, instance: GpuInstance) -> dict:
        """Get training status from an instance."""
        be = self.compute.get_backend(instance.backend)

        if instance.backend == "ssh":
            monitor_script = load_template("monitor_ssh.sh")
            rc, stdout, stderr = await be.exec(instance, monitor_script, timeout=30)
            return {"output": stdout, "error": stderr, "returncode": rc}

        elif instance.backend == "targon":
            health = await be.health_check(instance)
            return health

        return {"error": f"Unknown backend: {instance.backend}"}

