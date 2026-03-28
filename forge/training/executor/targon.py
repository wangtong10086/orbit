"""Compatibility wrapper over explicit Targon execution providers."""

from __future__ import annotations

from forge.config import ForgeConfig
from forge.foundation.contracts import TrainingSpec
from forge.training.providers import TargonBootstrapProvider, TargonImageProvider


class TargonExecutor:
    """Compatibility wrapper over explicit Targon providers."""

    def __init__(self, config: ForgeConfig, mode: str = "bootstrap"):
        self.config = config
        self.mode = mode

    async def launch(
        self,
        train_config,
        dataset_file: str,
        env_name: str,
        gpu_type: str = "H200",
        dataset_hf_repo: str = "",
        image: str | None = None,
    ):
        """Delegate launch to the explicitly selected Targon provider."""
        spec = TrainingSpec(
            experiment_id=env_name,
            model=train_config.model,
            dataset_path=dataset_file,
            train_config=train_config.__dict__.copy(),
            environments=(env_name,),
            output_dir=train_config.output_dir,
        )
        if self.mode == "bootstrap":
            provider = TargonBootstrapProvider(
                self.config,
                dataset_hf_repo=dataset_hf_repo,
                gpu_type=gpu_type,
                image=image or "pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel",
            )
        elif self.mode == "image":
            provider = TargonImageProvider(
                self.config,
                dataset_hf_repo=dataset_hf_repo,
                gpu_type=gpu_type,
                image=image or "wangtong123/affine-forge:latest",
            )
        else:
            raise ValueError(f"Unknown Targon executor mode: {self.mode}")
        return await provider.launch_training(spec)

    async def monitor(self, instance) -> dict:
        raise NotImplementedError("Use explicit Targon providers for monitoring")

    async def stop(self, instance) -> None:
        raise NotImplementedError("Use explicit Targon providers for stop/terminate")
