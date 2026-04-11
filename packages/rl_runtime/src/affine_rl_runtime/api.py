"""Public API for the Affine RL runtime layer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


TRAJECTORY_SCHEMA_VERSION = "trajectory.v1"
RUNTIME_LAUNCH_SCHEMA_VERSION = "runtime_launch.v1"
TOPOLOGY_SERVER = "server"
TOPOLOGY_COLOCATE = "colocate"


class TrajectoryStepV1(BaseModel):
    observation: Any
    action: Any
    reward: float
    done: bool
    telemetry: dict[str, Any] = Field(default_factory=dict)


class EpisodeArtifactRefV1(BaseModel):
    episode_id: str
    seed: int
    steps_path: str
    summary_path: str


class TrajectoryManifestV1(BaseModel):
    schema_version: Literal["trajectory.v1"] = TRAJECTORY_SCHEMA_VERSION
    env_pack_id: str
    env_pack_version: str
    episode_loop_version: str
    policy_version: str
    profile_id: str
    topology: str
    episodes: list[EpisodeArtifactRefV1] = Field(default_factory=list)


class WeightBusSpec(BaseModel):
    kind: str = "local_process"
    version: str = "weight_bus.v1"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactDestinations(BaseModel):
    training_log: str
    rollout_log: str = ""
    runtime_precheck_log: str = ""
    checkpoints_dir: str
    trajectory_manifest: str = ""


class RuntimeLaunchManifestV1(BaseModel):
    schema_version: Literal["runtime_launch.v1"] = RUNTIME_LAUNCH_SCHEMA_VERSION
    profile_id: str
    backend_kind: str
    env_pack_id: str
    env_pack_version: str
    episode_loop_version: str
    topology: str
    policy_version: str
    trajectory_schema_version: Literal["trajectory.v1"] = TRAJECTORY_SCHEMA_VERSION
    train_config_path: str
    dataset_path: str
    artifact_destinations: ArtifactDestinations
    weight_bus: WeightBusSpec = Field(default_factory=WeightBusSpec)
    extra: dict[str, Any] = Field(default_factory=dict)


class TopologyDriverSpec(BaseModel):
    kind: str
    description: str
    supports_external_rollout_server: bool = False
    supports_shared_weight_bus: bool = False


_TOPOLOGY_DRIVERS = (
    TopologyDriverSpec(
        kind=TOPOLOGY_SERVER,
        description="Dedicated rollout/runtime service topology.",
        supports_external_rollout_server=True,
        supports_shared_weight_bus=True,
    ),
    TopologyDriverSpec(
        kind=TOPOLOGY_COLOCATE,
        description="Colocated trainer/runtime topology sharing a local process group.",
        supports_external_rollout_server=False,
        supports_shared_weight_bus=True,
    ),
)


def list_topology_drivers() -> tuple[TopologyDriverSpec, ...]:
    return _TOPOLOGY_DRIVERS


def build_runtime_launch_manifest(
    *,
    profile_id: str,
    backend_kind: str,
    env_pack_id: str,
    env_pack_version: str,
    episode_loop_version: str,
    topology: str,
    policy_version: str,
    train_config_path: str,
    dataset_path: str,
    artifact_destinations: ArtifactDestinations,
    extra: dict[str, Any] | None = None,
) -> RuntimeLaunchManifestV1:
    return RuntimeLaunchManifestV1(
        profile_id=profile_id,
        backend_kind=backend_kind,
        env_pack_id=env_pack_id,
        env_pack_version=env_pack_version,
        episode_loop_version=episode_loop_version,
        topology=topology,
        policy_version=policy_version,
        train_config_path=train_config_path,
        dataset_path=dataset_path,
        artifact_destinations=artifact_destinations,
        extra=extra or {},
    )


def write_runtime_launch_manifest(path: str | Path, manifest: RuntimeLaunchManifestV1) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return target


def read_runtime_launch_manifest(path: str | Path) -> RuntimeLaunchManifestV1:
    return RuntimeLaunchManifestV1.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def write_trajectory_manifest(path: str | Path, manifest: TrajectoryManifestV1) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return target


def read_trajectory_manifest(path: str | Path) -> TrajectoryManifestV1:
    return TrajectoryManifestV1.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


__all__ = [
    "RUNTIME_LAUNCH_SCHEMA_VERSION",
    "TOPOLOGY_COLOCATE",
    "TOPOLOGY_SERVER",
    "TRAJECTORY_SCHEMA_VERSION",
    "ArtifactDestinations",
    "EpisodeArtifactRefV1",
    "RuntimeLaunchManifestV1",
    "TopologyDriverSpec",
    "TrajectoryManifestV1",
    "TrajectoryStepV1",
    "WeightBusSpec",
    "build_runtime_launch_manifest",
    "list_topology_drivers",
    "read_runtime_launch_manifest",
    "read_trajectory_manifest",
    "write_runtime_launch_manifest",
    "write_trajectory_manifest",
]
