"""Training pipeline orchestration over the execution plane."""

from __future__ import annotations

import tempfile

from forge.execution.bundle import JobBundle
from forge.execution.contracts import (
    DockerTarget,
    RunBundleRequest,
    RunHandle,
    RuntimeBackend,
    RuntimePreferences,
    RuntimeTarget,
    TargonProfile,
    TargonTarget,
    SshTarget,
)
from forge.execution.renderers import TrainTaskRenderer
from forge.foundation.contracts import TrainingSpec
from forge.training.config import SwiftConfig
from forge.training.sft import SwiftBackend


class TrainingPipeline:
    """Control-side training entrypoint over execution-plane runtimes."""

    def __init__(
        self,
        backend: SwiftBackend | None = None,
        renderer: TrainTaskRenderer | None = None,
    ):
        self.backend = backend or SwiftBackend()
        self.renderer = renderer or TrainTaskRenderer(self.backend)

    def validate_spec(self, spec: TrainingSpec) -> list[str]:
        """Validate a training spec before bundle render or launch."""

        config = spec.train_config
        issues = self.backend.validate_config(config)
        if not spec.dataset_path:
            issues.append("dataset_path is required")
        if not spec.output_dir:
            issues.append("output_dir is required")
        return issues

    def render_bundle(
        self,
        spec: TrainingSpec,
        *,
        bundle_dir: str,
        runtime_preferences: RuntimePreferences | None = None,
        overwrite: bool = False,
    ) -> JobBundle:
        """Render a training request into an execution-plane bundle."""

        issues = self.validate_spec(spec)
        if issues:
            raise ValueError(f"Training spec validation failed: {issues}")

        return self.renderer.render(
            bundle_dir,
            job_id=spec.experiment_id,
            dataset_path=spec.dataset_path,
            config=spec.train_config,
            runtime_preferences=runtime_preferences,
            overwrite=overwrite,
        )

    async def launch(
        self,
        spec: TrainingSpec,
        runtime_backend: RuntimeBackend,
        *,
        bundle_dir: str | None = None,
        target: RuntimeTarget | None = None,
    ) -> RunHandle:
        """Validate, render a bundle, then launch through the selected runtime."""

        actual_bundle_dir = bundle_dir or tempfile.mkdtemp(prefix=f"forge-train-{spec.experiment_id}-")
        runtime_preferences = RuntimePreferences(
            image=target.image if target is not None and hasattr(target, "image") else "",
            profile=(
                target.profile.value
                if target is not None and isinstance(target, TargonTarget) and isinstance(target.profile, TargonProfile)
                else getattr(target, "profile", "")
            ),
        )
        bundle = self.render_bundle(
            spec,
            bundle_dir=actual_bundle_dir,
            runtime_preferences=runtime_preferences,
            overwrite=True,
        )
        if target is None:
            target = DockerTarget()
        return await runtime_backend.run(
            RunBundleRequest(
                bundle_path=str(bundle.path),
                target=target,
            )
        )
