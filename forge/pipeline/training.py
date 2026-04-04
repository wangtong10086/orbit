"""Training pipeline orchestration over the execution plane."""

from __future__ import annotations

import tempfile

from forge.control.bundles import TrainBundleBuilder
from forge.execution.bundle import JobBundle
from forge.execution.contracts import (
    ExecutionBackend,
    ExecutionRequest,
    LaunchModeKind,
    LaunchModeSpec,
    PlacementKind,
    PlacementSpec,
    ResourceRequest,
)
from forge.foundation.contracts import TrainingSpec
from forge.training.sft import SwiftBackend


class TrainingPipeline:
    """Control-side training entrypoint over execution bundles and execution backends."""

    def __init__(self, backend: SwiftBackend | None = None, builder: TrainBundleBuilder | None = None):
        self.backend = backend or SwiftBackend()
        self.builder = builder or TrainBundleBuilder(self.backend)

    def validate_spec(self, spec: TrainingSpec) -> list[str]:
        issues = self.backend.validate_config(spec.train_config)
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
        resources: ResourceRequest | None = None,
        overwrite: bool = False,
    ) -> JobBundle:
        issues = self.validate_spec(spec)
        if issues:
            raise ValueError(f"Training spec validation failed: {issues}")
        return self.builder.build(bundle_dir, spec=spec, resources=resources, overwrite=overwrite)

    async def launch(
        self,
        spec: TrainingSpec,
        execution: ExecutionBackend,
        *,
        execution_request: ExecutionRequest | None = None,
        bundle_dir: str | None = None,
    ):
        actual_bundle_dir = bundle_dir or tempfile.mkdtemp(prefix=f"forge-train-{spec.experiment_id}-")
        if execution_request is None:
            execution_request = ExecutionRequest(
                bundle_path="",
                placement=PlacementSpec(kind=PlacementKind.LOCAL),
                launch_mode=LaunchModeSpec(kind=LaunchModeKind.HOST_PROCESS),
            )
        bundle = self.render_bundle(spec, bundle_dir=actual_bundle_dir, resources=execution_request.resources, overwrite=True)
        request = execution_request.model_copy(update={"bundle_path": str(bundle.path)})
        return await execution.run(request)
