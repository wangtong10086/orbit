"""Training pipeline runner."""

import os
import json
import asyncio
from pathlib import Path
from typing import Optional

from forge.config import ForgeConfig
from forge.compute.manager import ComputeManager
from forge.compute.base import GpuInstance
from forge.training.config import TrainConfig


class TrainingRunner:
    """Orchestrates the full training pipeline."""

    def __init__(self, config: ForgeConfig):
        self.config = config
        self.compute = ComputeManager(config)

    async def launch_on_ssh(
        self,
        instance: GpuInstance,
        dataset_path: str,
        train_config: Optional[TrainConfig] = None,
    ) -> None:
        """Launch training on an SSH-accessible instance."""
        tc = train_config or TrainConfig()

        # Generate and upload training script
        script = tc.to_train_script(dataset_path)
        local_script = "/tmp/train_sft.py"
        with open(local_script, "w") as f:
            f.write(script)

        be = self.compute.get_backend("ssh")
        await be.upload(instance, local_script, "/root/scripts/train_sft.py")

        # Launch in screen session
        cmd = "screen -dmS training bash -c 'python3 /root/scripts/train_sft.py 2>&1 | tee /root/training.log'"
        rc, stdout, stderr = await be.exec(instance, cmd, timeout=30)

        if rc == 0:
            print(f"Training launched on {instance.host}")
            print(f"  Monitor: forge train monitor {instance.id}")
        else:
            print(f"Failed to launch: {stderr}")

    async def launch_on_targon(
        self,
        env: str,
        train_config: Optional[TrainConfig] = None,
        gpu_type: str = "H200",
        dataset_hf_repo: str = os.environ.get("HF_DATASET_REPO", ""),
        dataset_file: Optional[str] = None,
    ) -> GpuInstance:
        """Launch training as a Targon serverless container.

        The container downloads data from HuggingFace, runs training,
        and pushes results back to HuggingFace.
        """
        tc = train_config or TrainConfig()
        if not tc.hf_backup_repo:
            tc.hf_backup_repo = self.config.hf_backup_repo or os.environ.get("HF_BACKUP_REPO", "")

        dataset_file = dataset_file or f"{env.lower()}_sft.jsonl"

        # Upload training script to HF first (keeps container args small)
        script = tc.to_train_script(f"/root/data/{dataset_file}")
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script)
            local_script = f.name

        from huggingface_hub import HfApi
        api = HfApi(token=self.config.hf_token)
        api.upload_file(
            path_or_fileobj=local_script,
            path_in_repo="train_sft.py",
            repo_id=dataset_hf_repo,
            repo_type="dataset",
        )
        os.unlink(local_script)
        print(f"Training script uploaded to {dataset_hf_repo}/train_sft.py")

        # pytorch image has torch pre-installed; download wheel bundle + data via urllib (reliable)
        # Status is written to /tmp/health/status.json for HTTP monitoring
        setup_and_train = (
            "mkdir -p /tmp/health && echo ok > /tmp/health/index.html && "
            "(python3 -m http.server 8080 --directory /tmp/health > /dev/null 2>&1 &) && "
            "echo '[HEALTH] HTTP health server started on :8080' && "
            "echo '{\"phase\":\"setup_start\"}' > /tmp/health/status.json && "
            "mkdir -p /root/checkpoints /root/data /root/scripts /tmp/wheels && "
            "echo '{\"phase\":\"torch_check\"}' > /tmp/health/status.json && "
            "echo '[SETUP] Checking torch...' && timeout 60 python3 -c 'import torch; print(torch.__version__, torch.cuda.is_available())' || echo '[WARN] torch check timed out, continuing' && "
            "echo '{\"phase\":\"downloading\"}' > /tmp/health/status.json && "
            "echo '[SETUP] Downloading wheel bundle + data from HF via urllib...' && "
            "python3 -c '"
            "import urllib.request, ssl, os, time, json\n"
            "ctx = ssl.create_default_context()\n"
            "tk = os.environ.get(\"HF_TOKEN\", \"\")\n"
            "hdr = {\"Authorization\": \"Bearer \" + tk, \"User-Agent\": \"python\"}\n"
            f"base = \"https://huggingface.co/datasets/{dataset_hf_repo}/resolve/main/\"\n"
            "files = [\n"
            f"    (\"ml-deps.tar.gz\", \"/tmp\"),\n"
            f"    (\"{dataset_file}\", \"/root/data\"),\n"
            f"    (\"train_sft.py\", \"/root/scripts\"),\n"
            "]\n"
            "for fn, d in files:\n"
            "    t0 = time.time()\n"
            "    json.dump({\"phase\": \"downloading\", \"file\": fn}, open(\"/tmp/health/status.json\", \"w\"))\n"
            "    req = urllib.request.Request(base + fn, headers=hdr)\n"
            "    data = urllib.request.urlopen(req, context=ctx, timeout=600).read()\n"
            "    open(d + \"/\" + fn, \"wb\").write(data)\n"
            "    print(f\"  Downloaded {fn} ({len(data)/1024/1024:.1f} MB, {time.time()-t0:.1f}s)\")\n"
            "' && "
            "echo '{\"phase\":\"extracting_wheels\"}' > /tmp/health/status.json && "
            "echo '[SETUP] Extracting wheels...' && "
            "tar xzf /tmp/ml-deps.tar.gz -C /tmp/wheels && "
            "echo '{\"phase\":\"pip_install\"}' > /tmp/health/status.json && "
            "echo '[SETUP] Installing deps from local wheels (offline)...' && "
            "pip install --no-index --find-links /tmp/wheels "
            "transformers==4.51.3 datasets accelerate peft trl==0.19.1 bitsandbytes huggingface_hub 2>&1 | tail -10 && "
            "rm -rf /tmp/wheels /tmp/ml-deps.tar.gz && "
            "test -f /root/data/" + dataset_file + " || { echo '{\"phase\":\"fatal\",\"error\":\"dataset_not_found\"}' > /tmp/health/status.json; echo '[FATAL] Dataset not downloaded'; exit 1; } && "
            "python3 -c 'import torch; import transformers; print(\"[SETUP] All deps verified\")' && "
            "echo '{\"phase\":\"deps_verified\"}' > /tmp/health/status.json && "
            "echo '[SETUP] Detecting GPUs...' && "
            "NUM_GPUS=$(python3 -c 'import torch; print(torch.cuda.device_count())') && "
            "echo \"[SETUP] Found $NUM_GPUS GPU(s). Launching training (single-GPU for QLoRA)...\" && "
            "CUDA_VISIBLE_DEVICES=0 python3 /root/scripts/train_sft.py 2>&1 | tee /root/training.log; "
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
                "DEBIAN_FRONTEND": "noninteractive",
            },
            port=8080,
        )

        print(f"Training container deployed on Targon")
        print(f"  ID: {instance.id}")
        print(f"  URL: {instance.url}")
        print(f"  GPU: {gpu_type}")
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

