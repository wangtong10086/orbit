"""Foundation contracts for the control-plane core."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Protocol, runtime_checkable

from pydantic import Field

from orbit.foundation.schema import FrozenModel, JsonValue
from orbit.training.config import LengthBucketingConfig, RolloutServerConfig, SwiftConfig


class ArtifactRef(FrozenModel):
    name: str
    uri: str
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class TrainingSpec(FrozenModel):
    experiment_id: str
    model: str
    dataset_path: str
    dataset_remote_repo: str = ""
    dataset_remote_path: str = ""
    dataset_remote_repo_type: str = "model"
    train_config: SwiftConfig
    train_config_effective: dict[str, JsonValue] = Field(default_factory=dict)
    train_config_runtime: dict[str, JsonValue] = Field(default_factory=dict)
    bucketing: LengthBucketingConfig | None = None
    bucketing_resolved: list[dict[str, JsonValue]] = Field(default_factory=list)
    rollout_server: RolloutServerConfig | None = None
    stage_local_backend_fork: bool = False
    profile_id: str = ""
    rl_profile: dict[str, JsonValue] = Field(default_factory=dict)
    environments: tuple[str, ...]
    output_dir: str

    def to_payload_dict(self) -> dict[str, JsonValue]:
        payload = self.model_dump(mode="json")
        effective = self.train_config_effective or self.train_config.to_effective_dict()
        payload["train_config"] = effective
        payload["train_config_effective"] = effective
        payload["train_config_runtime"] = self.train_config_runtime or self.train_config.model_dump(mode="json")
        return payload


class EvaluationSpec(FrozenModel):
    model_path: str
    environments: tuple[str, ...]
    samples_per_env: int = 100
    base_url: str = "http://172.17.0.1:30000/v1"
    output_dir: str = ""
    concurrency: int = 5
    seed: int = 42
    affinetes_dir: str = "/root/affinetes"
    api_key: str = ""
    skip_build: bool = False


@runtime_checkable
class ConversationPacker(Protocol):
    def pack(self, record: Mapping[str, JsonValue]) -> list[dict[str, JsonValue]]:
        ...


@runtime_checkable
class CanonicalRepository(Protocol):
    def exists(self, env_name: str, fingerprint: str) -> bool:
        ...

    def append(self, env_name: str, records: list[Mapping[str, JsonValue]]) -> int:
        ...

    def path_for(self, env_name: str) -> Path:
        ...


@runtime_checkable
class ArtifactStore(Protocol):
    def put_file(self, local_path: str, artifact_name: str) -> ArtifactRef:
        ...

    def fetch_file(self, artifact: ArtifactRef, local_path: str) -> str:
        ...


@runtime_checkable
class EvaluationRunner(Protocol):
    def run_evaluation(self, spec: EvaluationSpec):
        ...
