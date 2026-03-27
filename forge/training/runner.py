"""Training pipeline runner — orchestrates ms-swift training on remote machines."""

import os
import json
import asyncio
from pathlib import Path
from typing import Optional

from forge.config import ForgeConfig
from forge.compute.manager import ComputeManager
from forge.compute.base import GpuInstance
from forge.training.config import SwiftConfig


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
        cmd = f"screen -dmS training bash -c '{swift_cmd} 2>&1 | tee /root/training.log'"
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

        # Build swift command
        swift_cmd = tc.swift_command_from_yaml("/root/scripts/swift_config.yaml")

        # Container setup: install ms-swift, download data + config, run training
        setup_and_train = (
            "mkdir -p /tmp/health && echo ok > /tmp/health/index.html && "
            "(python3 -m http.server 8080 --directory /tmp/health > /dev/null 2>&1 &) && "
            "echo '[HEALTH] HTTP health server started on :8080' && "
            "echo '{\"phase\":\"setup_start\"}' > /tmp/health/status.json && "
            "mkdir -p /root/checkpoints /root/data /root/scripts && "
            # Install ms-swift and deepspeed
            "echo '{\"phase\":\"installing_swift\"}' > /tmp/health/status.json && "
            "echo '[SETUP] Installing ms-swift + deepspeed...' && "
            "pip install ms-swift deepspeed -U 2>&1 | tail -5 && "
            # Download dataset and config from HF (using Python huggingface_hub)
            "echo '{\"phase\":\"downloading\"}' > /tmp/health/status.json && "
            "echo '[SETUP] Downloading data + config from HF...' && "
            "python3 -c '"
            "from huggingface_hub import hf_hub_download\n"
            "import os, time, json\n"
            "token = os.environ.get(\"HF_TOKEN\", \"\")\n"
            f"repo = \"{dataset_hf_repo}\"\n"
            "files = [\n"
            f"    (\"{dataset_file}\", \"/root/data/{dataset_file}\"),\n"
            "    (\"swift_config.yaml\", \"/root/scripts/swift_config.yaml\"),\n"
            "]\n"
            "for remote, local in files:\n"
            "    t0 = time.time()\n"
            "    json.dump({\"phase\": \"downloading\", \"file\": remote}, open(\"/tmp/health/status.json\", \"w\"))\n"
            "    print(f\"  Downloading {remote}...\")\n"
            "    path = hf_hub_download(repo_id=repo, filename=remote, repo_type=\"dataset\", token=token, local_dir=\"/root/hf_cache\")\n"
            "    import shutil\n"
            "    shutil.copy2(path, local)\n"
            "    sz = os.path.getsize(local) / 1024 / 1024\n"
            "    print(f\"  Downloaded {remote} ({sz:.1f} MB, {time.time()-t0:.1f}s)\")\n"
            "' && "
            "test -f /root/data/" + dataset_file + " || { echo '{\"phase\":\"fatal\",\"error\":\"dataset_not_found\"}' > /tmp/health/status.json; echo '[FATAL] Dataset not downloaded'; exit 1; } && "
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
            "if [ $EXIT_CODE -eq 0 ]; then echo 'TRAINING_COMPLETE'; else echo 'TRAINING_FAILED'; sleep 3600; fi"
        )

        targon = self.compute.get_backend("targon")
        instance = await targon.provision(
            gpu_type=gpu_type,
            name=f"affine-train-{env.lower()}",
            image="pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel",
            command=["/bin/bash", "-c"],
            args=[setup_and_train],
            env={
                "HF_TOKEN": self.config.hf_token,
                "HF_BACKUP_REPO": tc.hf_backup_repo,
                "NPROC_PER_NODE": str(tc.num_gpus),
                "DEBIAN_FRONTEND": "noninteractive",
            },
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
            rc, stdout, stderr = await be.exec(instance, """
echo "=== Training Status ==="
if screen -list | grep -q training; then
    echo "Status: RUNNING"
    echo ""
    echo "=== Last 20 lines ==="
    tail -20 /root/training.log 2>/dev/null || echo "No log file"
    echo ""
    echo "=== GPU Usage ==="
    nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader 2>/dev/null || echo "No GPU"
    echo ""
    echo "=== Checkpoints ==="
    ls -lt /root/checkpoints/ 2>/dev/null | head -5 || echo "No checkpoints"
else
    echo "Status: NOT RUNNING"
    tail -20 /root/training.log 2>/dev/null || echo "No log file"
fi
""", timeout=30)
            return {"output": stdout, "error": stderr, "returncode": rc}

        elif instance.backend == "targon":
            health = await be.health_check(instance)
            return health

        return {"error": f"Unknown backend: {instance.backend}"}

