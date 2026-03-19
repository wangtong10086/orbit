"""Centralized configuration for Affine Forge."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).parent.parent


def _load_dotenv():
    """Load .env file from project root or parent directory."""
    for env_path in [PROJECT_ROOT / ".env", PROJECT_ROOT.parent / ".env"]:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key and key not in os.environ:
                            os.environ[key] = value
            return


@dataclass
class ForgeConfig:
    """All configuration in one place."""

    # Affine API
    api_url: str = "https://api.affine.io/api/v1"

    # HuggingFace
    hf_token: str = ""
    hf_backup_repo: str = ""

    # Targon GPU Cloud
    targon_api_key: str = ""

    # Chutes AI
    chutes_api_key: str = ""

    # Identity
    my_hotkey: str = ""
    my_uid: str = ""

    # Paths
    project_root: Path = field(default_factory=lambda: PROJECT_ROOT)
    data_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data")
    machines_file: Path = field(default_factory=lambda: PROJECT_ROOT / "machines.json")
    backup_dir: Path = field(default_factory=lambda: Path.home() / "backups" / "checkpoints")

    # Optional
    wandb_api_key: str = ""

    @classmethod
    def load(cls) -> "ForgeConfig":
        """Load config from environment variables and .env file."""
        _load_dotenv()

        return cls(
            api_url=os.getenv("API_URL", "https://api.affine.io/api/v1"),
            hf_token=os.getenv("HF_TOKEN", ""),
            hf_backup_repo=os.getenv("HF_BACKUP_REPO", ""),
            targon_api_key=os.getenv("TARGON_API_KEY", ""),
            chutes_api_key=os.getenv("CHUTES_API_KEY", ""),
            my_hotkey=os.getenv("MY_HOTKEY", ""),
            my_uid=os.getenv("MY_UID", ""),
            wandb_api_key=os.getenv("WANDB_API_KEY", ""),
        )
