"""Training backend protocol — defines the interface for training methods.

Each training method (SFT, RLHF, etc.) generates a swift CLI command
or YAML config. Executors (Targon, SSH) handle running on remote machines.
"""

from __future__ import annotations

from typing import Protocol

from forge.training.config import SwiftConfig


class TrainBackend(Protocol):
    """Protocol for training method implementations.

    Each implementation generates ms-swift CLI commands or YAML configs.
    """

    def generate_command(self, config: SwiftConfig, dataset_path: str) -> str:
        """Generate the swift CLI command string.

        Args:
            config: Swift training configuration
            dataset_path: Path to dataset (on the remote machine)
        Returns:
            Complete swift CLI command string
        """
        ...

    def generate_yaml(self, config: SwiftConfig, dataset_path: str) -> str:
        """Generate YAML config content for ms-swift.

        Args:
            config: Swift training configuration
            dataset_path: Path to dataset (on the remote machine)
        Returns:
            YAML config string
        """
        ...

    def validate_config(self, config: SwiftConfig) -> list[str]:
        """Validate config for this training method. Returns list of issues."""
        ...
