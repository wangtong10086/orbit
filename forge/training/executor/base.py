"""Executor protocol — interface for running training scripts on compute backends."""

from __future__ import annotations

from typing import Protocol, Optional

from forge.compute.base import GpuInstance


class ExecutorProtocol(Protocol):
    """Protocol for training execution backends.

    Each executor knows how to deploy, run, and monitor training
    scripts on a specific compute backend.
    """

    async def launch(
        self,
        script: str,
        dataset_path: str,
        env_name: str,
        gpu_type: str = "H200",
        **kwargs,
    ) -> GpuInstance:
        """Deploy and launch a training script.

        Args:
            script: Complete Python training script
            dataset_path: Remote path to dataset
            env_name: Environment name (for labeling)
            gpu_type: GPU type to provision
            **kwargs: Backend-specific options

        Returns:
            GpuInstance representing the training job
        """
        ...

    async def monitor(self, instance: GpuInstance) -> dict:
        """Get training status from an instance."""
        ...

    async def stop(self, instance: GpuInstance) -> None:
        """Stop a running training job."""
        ...
