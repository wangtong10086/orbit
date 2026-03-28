"""Compatibility wrapper over the unified training pipeline."""

import os
from typing import Optional

from forge.config import ForgeConfig
from forge.compute.base import GpuInstance
from forge.foundation.contracts import TrainingSpec
from forge.pipeline.training import TrainingPipeline
from forge.training.config import SwiftConfig
from forge.training.providers import (
    SshExecutionProvider,
    TargonBootstrapProvider,
    TargonImageProvider,
)
from forge.data.aggregate import build_from_canonical, upload_merged


# Alias for backward compatibility
TrainConfig = SwiftConfig


class TrainingRunner:
    """Compatibility wrapper that delegates to TrainingPipeline."""

    def __init__(self, config: ForgeConfig):
        self.config = config
        self.pipeline = TrainingPipeline()

    def _training_spec(
        self,
        *,
        experiment_id: str,
        dataset_path: str,
        train_config: SwiftConfig,
        environments: tuple[str, ...] = (),
    ) -> TrainingSpec:
        return TrainingSpec(
            experiment_id=experiment_id,
            model=train_config.model,
            dataset_path=dataset_path,
            train_config=train_config.__dict__.copy(),
            environments=environments,
            output_dir=train_config.output_dir,
        )

    async def launch_on_ssh(
        self,
        instance: GpuInstance,
        dataset_path: str,
        train_config: Optional[SwiftConfig] = None,
    ):
        """Launch training through the explicit SSH execution provider."""
        tc = train_config or SwiftConfig()
        provider = SshExecutionProvider(self.config, instance=instance)
        spec = self._training_spec(
            experiment_id=instance.id,
            dataset_path=dataset_path,
            train_config=tc,
        )
        return await self.pipeline.launch(spec, provider)

    async def launch_on_targon(
        self,
        env: str,
        train_config: Optional[SwiftConfig] = None,
        gpu_type: str = "H200",
        dataset_hf_repo: str = os.environ.get("HF_DATASET_REPO", ""),
        dataset_file: Optional[str] = None,
        provider_mode: str = "bootstrap",
        image: str | None = None,
    ):
        """Launch training through an explicit Targon provider."""
        tc = train_config or SwiftConfig()
        dataset_file = dataset_file or f"{env.lower()}_sft.jsonl"
        spec = self._training_spec(
            experiment_id=env.replace("/", "-"),
            dataset_path=dataset_file,
            train_config=tc,
            environments=(env,),
        )
        if provider_mode == "bootstrap":
            provider = TargonBootstrapProvider(
                self.config,
                dataset_hf_repo=dataset_hf_repo,
                gpu_type=gpu_type,
                image=image or "pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel",
            )
        elif provider_mode == "image":
            provider = TargonImageProvider(
                self.config,
                dataset_hf_repo=dataset_hf_repo,
                gpu_type=gpu_type,
                image=image or "wangtong123/affine-forge:latest",
            )
        else:
            raise ValueError(f"Unknown Targon provider mode: {provider_mode}")
        return await self.pipeline.launch(spec, provider)

    async def monitor(self, launch) -> dict:
        """Monitor an existing training launch."""
        provider = launch.provider_name
        if provider == "ssh":
            instance = GpuInstance(
                id=launch.run_id,
                backend="ssh",
                gpu_type="unknown",
                status=launch.status,
                host=launch.metadata.get("host"),
                port=launch.metadata.get("port", 22),
                user=launch.metadata.get("user", "root"),
                metadata={"key": launch.metadata.get("key", "")},
            )
            return await SshExecutionProvider(self.config, instance).monitor_training(launch)
        if provider == "targon-bootstrap":
            return await TargonBootstrapProvider(
                self.config,
                dataset_hf_repo=launch.metadata.get("dataset_repo", ""),
                gpu_type=launch.metadata.get("gpu_type", "H200"),
                image=launch.metadata.get("image", "pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel"),
            ).monitor_training(launch)
        if provider == "targon-image":
            return await TargonImageProvider(
                self.config,
                dataset_hf_repo=launch.metadata.get("dataset_repo", ""),
                gpu_type=launch.metadata.get("gpu_type", "H200"),
                image=launch.metadata.get("image", "wangtong123/affine-forge:latest"),
            ).monitor_training(launch)
        return {"error": f"Unknown provider: {provider}"}

    async def prepare_dataset(
        self,
        env: str,
        min_score: float = 0.5,
        output: str | None = None,
        max_samples: int = 0,
    ) -> dict:
        """Build a local training dataset from canonical repository data."""
        output_path = output or f"data/{env.lower().replace('-', '_')}_train.jsonl"
        return build_from_canonical(
            output_path=output_path,
            envs=[env],
            min_score=min_score,
            max_samples_per_env=max_samples,
        )

    async def full_pipeline(
        self,
        env: str,
        gpu_type: str = "H200",
        min_score: float = 0.5,
        provider: str = "targon-bootstrap",
        max_samples: int = 0,
        dataset_repo: str | None = None,
        image: str | None = None,
    ):
        """Build dataset, optionally upload it, then launch through one provider."""
        output = f"data/{env.lower().replace('-', '_')}_train.jsonl"
        stats = await self.prepare_dataset(env, min_score=min_score, output=output, max_samples=max_samples)
        dataset_repo = dataset_repo or os.environ.get("HF_DATASET_REPO", "")
        if provider.startswith("targon"):
            if not self.config.hf_token or not dataset_repo:
                raise ValueError("HF_TOKEN and HF_DATASET_REPO are required for Targon training")
            upload_merged(output, token=self.config.hf_token, remote_filename=os.path.basename(output), repo_id=dataset_repo)
            tc = SwiftConfig()
            return await self.launch_on_targon(
                env=env,
                train_config=tc,
                gpu_type=gpu_type,
                dataset_hf_repo=dataset_repo,
                dataset_file=os.path.basename(output),
                provider_mode="bootstrap" if provider == "targon-bootstrap" else "image",
                image=image,
            )
        raise ValueError("full_pipeline currently requires explicit Targon provider selection")
