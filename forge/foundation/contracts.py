"""Foundation contracts for the three-layer refactor.

These are interface-level contracts only. They describe stable boundaries used
by pipelines and agents, but they do not pretend to be production execution
implementations on their own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable


@dataclass(frozen=True)
class ArtifactRef:
    """Canonical reference to an artifact stored outside the caller."""

    name: str
    uri: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrainingSpec:
    """Stable training request contract for pipeline and provider boundaries."""

    experiment_id: str
    model: str
    dataset_path: str
    train_config: Mapping[str, Any]
    environments: tuple[str, ...]
    output_dir: str


@dataclass(frozen=True)
class TrainingLaunch:
    """Opaque handle for a launched training run."""

    provider_name: str
    run_id: str
    status: str = "submitted"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationSpec:
    """Stable evaluation request contract."""

    model_path: str
    environments: tuple[str, ...]
    samples_per_env: int = 100


@runtime_checkable
class ConversationPacker(Protocol):
    """Environment- or model-aware conversation packing contract."""

    def pack(self, record: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Return packed messages ready for dataset build."""
        ...


@runtime_checkable
class CanonicalRepository(Protocol):
    """Canonical data storage contract."""

    def exists(self, env_name: str, fingerprint: str) -> bool:
        """Return whether a canonical entry already exists."""
        ...

    def append(self, env_name: str, records: list[Mapping[str, Any]]) -> int:
        """Persist canonical records and return the count written."""
        ...

    def path_for(self, env_name: str) -> Path:
        """Return the canonical storage path for an environment."""
        ...


@runtime_checkable
class ExecutionProvider(Protocol):
    """Execution boundary for launching training or evaluation workloads."""

    async def launch_training(self, spec: TrainingSpec) -> TrainingLaunch:
        """Launch a training workload and return an opaque run handle."""
        ...

    async def monitor_training(self, launch: TrainingLaunch) -> dict[str, Any]:
        """Return provider-specific training status for a launched run."""
        ...


@runtime_checkable
class ArtifactStore(Protocol):
    """Artifact persistence boundary."""

    def put_file(self, local_path: str, artifact_name: str) -> ArtifactRef:
        """Store a local artifact and return a canonical reference."""
        ...

    def fetch_file(self, artifact: ArtifactRef, local_path: str) -> str:
        """Materialize an artifact locally and return the output path."""
        ...


@runtime_checkable
class EvaluationRunner(Protocol):
    """Evaluation execution boundary."""

    def run_evaluation(self, spec: EvaluationSpec):
        """Run evaluation for a model according to the given spec."""
        ...
