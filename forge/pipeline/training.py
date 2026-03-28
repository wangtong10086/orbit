"""Training pipeline orchestration over explicit execution providers."""

from __future__ import annotations

from forge.foundation.contracts import ExecutionProvider, TrainingLaunch, TrainingSpec
from forge.training.config import SwiftConfig
from forge.training.sft import SwiftBackend


class TrainingPipeline:
    """Single orchestration entrypoint for training launches."""

    def __init__(self, backend: SwiftBackend | None = None):
        self.backend = backend or SwiftBackend()

    def validate_spec(self, spec: TrainingSpec) -> list[str]:
        """Validate a training spec before provider launch."""

        config = SwiftConfig(**spec.train_config)
        issues = self.backend.validate_config(config)
        if not spec.dataset_path:
            issues.append("dataset_path is required")
        if not spec.output_dir:
            issues.append("output_dir is required")
        return issues

    async def launch(
        self,
        spec: TrainingSpec,
        provider: ExecutionProvider,
    ) -> TrainingLaunch:
        """Validate then launch through the explicitly selected provider."""

        issues = self.validate_spec(spec)
        if issues:
            raise ValueError(f"Training spec validation failed: {issues}")
        return await provider.launch_training(spec)
