"""Centralized configuration for Affine Forge."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).parent.parent


def _load_dotenv():
    """Load .env file from project root or parent directory."""
    for env_path in [PROJECT_ROOT / ".env", PROJECT_ROOT.parent / ".env"]:
        if env_path.exists():
            with env_path.open(encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value
            return


class ForgeConfig(BaseSettings):
    """All configuration in one place."""

    model_config = SettingsConfigDict(
        extra="ignore",
        arbitrary_types_allowed=True,
        validate_assignment=True,
    )

    api_url: str = Field(default="https://api.affine.io/api/v1", validation_alias="API_URL")
    hf_token: str = Field(default="", validation_alias="HF_TOKEN")
    hf_backup_repo: str = Field(default="", validation_alias="HF_BACKUP_REPO")
    targon_api_key: str = Field(default="", validation_alias="TARGON_API_KEY")
    chutes_api_key: str = Field(default="", validation_alias="CHUTES_API_KEY")
    my_hotkey: str = Field(default="", validation_alias="MY_HOTKEY")
    my_uid: str = Field(default="", validation_alias="MY_UID")
    wandb_api_key: str = Field(default="", validation_alias="WANDB_API_KEY")

    project_root: Path = Field(default_factory=lambda: PROJECT_ROOT)
    data_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "data")
    machines_file: Path = Field(default_factory=lambda: PROJECT_ROOT / "machines.json")
    backup_dir: Path = Field(default_factory=lambda: Path.home() / "backups" / "checkpoints")

    @classmethod
    def load(cls) -> "ForgeConfig":
        """Load config from environment variables and .env file."""
        _load_dotenv()
        return cls()
