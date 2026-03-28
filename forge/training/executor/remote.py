"""Compatibility wrapper over SshExecutionProvider."""

from __future__ import annotations

from forge.compute.base import GpuInstance
from forge.config import ForgeConfig
from forge.training.providers import SshExecutionProvider


class RemoteExecutor:
    """Compatibility wrapper over the explicit SSH provider."""

    def __init__(self, config: ForgeConfig):
        self.config = config

    async def launch(
        self,
        script: str,
        dataset_path: str,
        env_name: str,
        instance: GpuInstance,
        **kwargs,
    ):
        """Compatibility shim retained only for older imports."""
        raise NotImplementedError(
            "RemoteExecutor is deprecated. Use TrainingPipeline + SshExecutionProvider."
        )

    async def monitor(self, instance) -> dict:
        raise NotImplementedError("Use SshExecutionProvider directly for monitoring")

    async def stop(self, instance) -> None:
        raise NotImplementedError("Use SshExecutionProvider directly for stopping")
