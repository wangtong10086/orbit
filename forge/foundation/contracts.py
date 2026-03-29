"""Foundation contracts for the control-plane core."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Protocol, runtime_checkable

from pydantic import Field

from forge.foundation.schema import FrozenModel, JsonValue
from forge.training.config import SwiftConfig


class ArtifactRef(FrozenModel):
    name: str
    uri: str
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class TrainingSpec(FrozenModel):
    experiment_id: str
    model: str
    dataset_path: str
    train_config: SwiftConfig
    environments: tuple[str, ...]
    output_dir: str


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
