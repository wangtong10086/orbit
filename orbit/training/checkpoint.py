"""Checkpoint backup and HuggingFace upload management."""

import os
import time
from pathlib import Path
from typing import Optional

from orbit.config import OrbitConfig
from orbit.compute.base import GpuInstance


class CheckpointManager:
    """Manages checkpoint backup and HuggingFace uploads."""

    def __init__(self, config: OrbitConfig):
        self.config = config
        self.backup_dir = config.backup_dir

    async def backup_from_ssh(
        self,
        instance: GpuInstance,
        backend,
        remote_dir: str = "/root/checkpoints",
    ) -> Optional[Path]:
        """Download latest checkpoint from SSH instance."""
        # Find latest checkpoint
        rc, stdout, _ = await backend.exec(
            instance, f"ls -td {remote_dir}/*/ 2>/dev/null | head -1", timeout=15
        )
        if rc != 0 or not stdout.strip():
            print(f"No checkpoints found at {remote_dir}")
            return None

        latest = stdout.strip()
        print(f"Latest checkpoint: {latest}")

        # Download
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        local_dir = self.backup_dir / instance.id / timestamp
        os.makedirs(local_dir, exist_ok=True)

        print(f"Backing up to {local_dir}...")
        await backend.download(instance, latest, str(local_dir))
        print(f"Backup complete: {local_dir}")

        return local_dir

    async def push_to_hf(self, local_path: Path, tag: str = "") -> str:
        """Upload checkpoint directory to HuggingFace."""
        if not self.config.hf_backup_repo or not self.config.hf_token:
            raise ValueError("HF_BACKUP_REPO and HF_TOKEN required for HuggingFace upload")

        from huggingface_hub import HfApi
        api = HfApi(token=self.config.hf_token)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path_in_repo = f"checkpoints/{tag}/{timestamp}" if tag else f"checkpoints/{timestamp}"

        print(f"Pushing to {self.config.hf_backup_repo}:{path_in_repo}...")
        api.upload_folder(
            folder_path=str(local_path),
            repo_id=self.config.hf_backup_repo,
            path_in_repo=path_in_repo,
            repo_type="model",
        )
        print("HuggingFace upload complete")
        return path_in_repo

    async def backup_and_push(
        self,
        instance: GpuInstance,
        backend,
        remote_dir: str = "/root/checkpoints",
        tag: str = "",
    ) -> Optional[str]:
        """Backup from instance and push to HuggingFace."""
        local_path = await self.backup_from_ssh(instance, backend, remote_dir)
        if not local_path:
            return None

        if self.config.hf_backup_repo and self.config.hf_token:
            return await self.push_to_hf(local_path, tag)

        return str(local_path)
