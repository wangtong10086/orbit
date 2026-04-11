"""Versioned config schema for one-command training launches."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import Field

from orbit.core.contracts.execution import ResourceRequest
from orbit.foundation.schema import StrictModel
from orbit.training.config import LengthBucketingConfig, RolloutServerConfig, SwiftConfig


class ExperimentLaunchSpec(StrictModel):
    id: str
    variable: str
    hypothesis: str
    notes: str = ""
    status: str = "draft"


class LocalDatasetSource(StrictModel):
    kind: Literal["local_file"] = "local_file"
    label: str = "DATA"
    path: str
    count: int = 0


class HuggingFaceDatasetSource(StrictModel):
    kind: Literal["hf_dataset_file"] = "hf_dataset_file"
    label: str = "DATA"
    repo_id: str
    filename: str
    revision: str = "main"
    count: int = 0


DatasetSource = Annotated[LocalDatasetSource | HuggingFaceDatasetSource, Field(discriminator="kind")]


class RegisteredMachineTarget(StrictModel):
    kind: Literal["registered_machine"] = "registered_machine"
    machine_name: str


class ProvisionTargonSshRentalTarget(StrictModel):
    kind: Literal["provision_targon_ssh_rental"] = "provision_targon_ssh_rental"
    workload_name: str
    machine_name: str
    resource: str = "h200-small"
    image: str = ""
    project_id: str = ""
    ssh_key_uid: str = ""
    public_key: str = "~/.ssh/id_ed25519.pub"
    ssh_port: int = 2222
    use_ssh_daemon: bool = True
    wait: bool = True
    timeout_seconds: int = 900
    poll_seconds: int = 10


ExecutionTarget = Annotated[RegisteredMachineTarget | ProvisionTargonSshRentalTarget, Field(discriminator="kind")]


class TrainingPublishSpec(StrictModel):
    push_to_hub: bool = False
    hub_model_id: str = ""
    create_repo: bool = False
    private: bool = True


class TrainingExecutionLaunchSpec(StrictModel):
    template_id: str
    bundle_dir: str = ""
    image: str = ""
    detach: bool = True
    stage_local_backend_fork: bool = False
    runtime_env: dict[str, str] = Field(default_factory=dict)
    resources: ResourceRequest = Field(default_factory=ResourceRequest)
    target: ExecutionTarget | None = None


class TrainingLaunchConfig(StrictModel):
    version: int = 1
    kind: Literal["training_launch"] = "training_launch"
    required_env: tuple[str, ...] = ()
    experiment: ExperimentLaunchSpec
    dataset: DatasetSource
    training: SwiftConfig
    bucketing: LengthBucketingConfig | None = None
    rollout_server: RolloutServerConfig | None = None
    publish: TrainingPublishSpec = Field(default_factory=TrainingPublishSpec)
    execution: TrainingExecutionLaunchSpec


def load_training_launch_config(path: str | Path) -> TrainingLaunchConfig:
    target = Path(path)
    with target.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return TrainingLaunchConfig.model_validate(payload)


__all__ = [
    "DatasetSource",
    "ExecutionTarget",
    "ExperimentLaunchSpec",
    "HuggingFaceDatasetSource",
    "LocalDatasetSource",
    "ProvisionTargonSshRentalTarget",
    "RegisteredMachineTarget",
    "TrainingExecutionLaunchSpec",
    "TrainingLaunchConfig",
    "TrainingPublishSpec",
    "load_training_launch_config",
]
