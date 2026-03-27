"""Targon executor — runs ms-swift training on Targon serverless containers.

Wraps forge.compute.targon with training-specific logic:
- Generate swift YAML config and upload to HF
- Build container command for ms-swift training
- Launch, monitor, and stop instances
"""

from __future__ import annotations

import os
import tempfile

from forge.compute.base import GpuInstance
from forge.config import ForgeConfig
from forge.training.config import SwiftConfig


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

        # Build container setup + training command
        swift_cmd = train_config.swift_command_from_yaml("/root/scripts/swift_config.yaml")
        setup_and_train = self._build_container_command(
            dataset_hf_repo, dataset_file, swift_cmd
        )

        compute = ComputeManager(self.config)
        targon = compute.get_backend("targon")
        instance = await targon.provision(
            gpu_type=gpu_type,
            name=f"affine-train-{env_name.lower()}",
            image="pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel",
            command=["/bin/bash", "-c"],
            args=[setup_and_train],
            env={
                "HF_TOKEN": self.config.hf_token,
                "HF_BACKUP_REPO": train_config.hf_backup_repo,
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

    def _build_container_command(
        self, dataset_hf_repo: str, dataset_file: str, swift_cmd: str
    ) -> str:
        """Build the bash command for the Targon container.

        The container:
        1. Starts a health check server on :8080
        2. Installs ms-swift
        3. Downloads dataset + YAML config from HF
        4. Runs ms-swift training
        5. Uploads training log to HF
        """
        return (
            "mkdir -p /tmp/health && echo ok > /tmp/health/index.html && "
            "(python3 -m http.server 8080 --directory /tmp/health > /dev/null 2>&1 &) && "
            "echo '[HEALTH] HTTP health server started on :8080' && "
            "echo '{\"phase\":\"setup_start\"}' > /tmp/health/status.json && "
            "mkdir -p /root/checkpoints /root/data /root/scripts && "
            # Install ms-swift
            "echo '{\"phase\":\"installing_swift\"}' > /tmp/health/status.json && "
            "echo '[SETUP] Installing ms-swift...' && "
            "pip install ms-swift -U 2>&1 | tail -5 && "
            # Download dataset and config from HF
            "echo '{\"phase\":\"downloading\"}' > /tmp/health/status.json && "
            "echo '[SETUP] Downloading data + config from HF...' && "
            "python3 -c '"
            "import urllib.request, ssl, os, time, json\n"
            "ctx = ssl.create_default_context()\n"
            "tk = os.environ.get(\"HF_TOKEN\", \"\")\n"
            "hdr = {\"Authorization\": \"Bearer \" + tk, \"User-Agent\": \"python\"}\n"
            f"base = \"https://huggingface.co/datasets/{dataset_hf_repo}/resolve/main/\"\n"
            "files = [\n"
            f"    (\"{dataset_file}\", \"/root/data\"),\n"
            "    (\"swift_config.yaml\", \"/root/scripts\"),\n"
            "]\n"
            "for fn, d in files:\n"
            "    t0 = time.time()\n"
            "    json.dump({\"phase\": \"downloading\", \"file\": fn}, open(\"/tmp/health/status.json\", \"w\"))\n"
            "    req = urllib.request.Request(base + fn, headers=hdr)\n"
            "    data = urllib.request.urlopen(req, context=ctx, timeout=600).read()\n"
            "    open(d + \"/\" + fn, \"wb\").write(data)\n"
            "    print(f\"  Downloaded {fn} ({len(data)/1024/1024:.1f} MB, {time.time()-t0:.1f}s)\")\n"
            "' && "
            f"test -f /root/data/{dataset_file} || "
            "{ echo '{\"phase\":\"fatal\",\"error\":\"dataset_not_found\"}' > /tmp/health/status.json; "
            "echo '[FATAL] Dataset not downloaded'; exit 1; } && "
            "echo '{\"phase\":\"deps_verified\"}' > /tmp/health/status.json && "
            "echo '[SETUP] Launching ms-swift training...' && "
            "echo '{\"phase\":\"training\"}' > /tmp/health/status.json && "
            f"{swift_cmd} 2>&1 | tee /root/training.log; "
            "EXIT_CODE=$?; "
            "echo \"[EXIT] Training exited with code $EXIT_CODE\"; "
            "python3 -c \""
            "from huggingface_hub import HfApi; "
            "import os; api = HfApi(token=os.environ.get('HF_TOKEN','')); "
            "api.upload_file(path_or_fileobj='/root/training.log', path_in_repo='training.log', "
            "repo_id=os.environ.get('HF_BACKUP_REPO',''), repo_type='model'); "
            "print('[LOG] Training log uploaded to HF')\" || true; "
            "if [ $EXIT_CODE -eq 0 ]; then echo 'TRAINING_COMPLETE'; "
            "else echo 'TRAINING_FAILED'; sleep 3600; fi"
        )
