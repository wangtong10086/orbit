"""Stable execution-plane contracts."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Protocol, runtime_checkable
import time

from pydantic import Field, StringConstraints

from forge.foundation.schema import FrozenModel, RequestContext
from forge.training.config import SwiftConfig


EnvKey = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]*$")]


class JobKind(str, Enum):
    TRAIN = "train"
    EVAL = "eval"
    COLLECT = "collect"


class RunState(str, Enum):
    PREPARED = "prepared"
    SUBMITTED = "submitted"
    PROVISIONING = "provisioning"
    STARTING = "starting"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TERMINATED = "terminated"


class TargonProfile(str, Enum):
    BOOTSTRAP = "bootstrap"
    IMAGE = "image"


class ResourceRequest(FrozenModel):
    gpu_type: str = "unknown"
    gpu_count: int = 1
    cpu_count: int = 0
    memory_gb: int = 0


class RuntimePreferences(FrozenModel):
    image: str = ""
    profile: str = ""
    runtime_env: dict[EnvKey, str] = Field(default_factory=dict)


class InputRef(FrozenModel):
    name: str
    relative_path: str
    required: bool = True


class OutputRef(FrozenModel):
    name: str
    relative_path: str
    kind: str = "file"


class TrainTaskSpec(FrozenModel):
    model: str
    dataset_filename: str
    train_config: SwiftConfig
    config_filename: str = "swift_config.yaml"
    train_type: str = "sft"


class EvalTaskSpec(FrozenModel):
    model: str
    environments: tuple[str, ...]
    samples: int = 100
    base_url: str = "http://172.17.0.1:30000/v1"
    concurrency: int = 5
    seed: int = 42
    affinetes_dir: str = "/root/affinetes"
    api_key: str = ""
    skip_build: bool = True
    output_subdir: str = "eval"


class NavworldCollectConfig(FrozenModel):
    num: int = 10
    model: str = "qwen3-max"
    start_id: int = 0
    concurrency: int = 3
    problem_type: str | None = None
    phase1: bool = False


class CollectTaskSpec(FrozenModel):
    collector: str = "navworld-gen"
    output_filename: str
    config: NavworldCollectConfig = Field(default_factory=NavworldCollectConfig)


TaskSpec = TrainTaskSpec | EvalTaskSpec | CollectTaskSpec


class JobSpec(FrozenModel):
    job_id: str
    kind: JobKind
    resources: ResourceRequest = Field(default_factory=ResourceRequest)
    runtime_preferences: RuntimePreferences = Field(default_factory=RuntimePreferences)
    inputs: tuple[InputRef, ...] = Field(default_factory=tuple)
    expected_outputs: tuple[OutputRef, ...] = Field(default_factory=tuple)
    task: TaskSpec | None = None


class DockerTarget(FrozenModel):
    runtime_name: Literal["docker"] = "docker"
    target: str = ""
    image: str = ""
    detach: bool = True


class SshTarget(FrozenModel):
    runtime_name: Literal["ssh"] = "ssh"
    target: str
    profile: str = ""
    image: str = ""
    gpu_type: str = ""
    dataset_repo: str = ""
    detach: bool = True


class TargonTarget(FrozenModel):
    runtime_name: Literal["targon"] = "targon"
    target: str = ""
    profile: TargonProfile = TargonProfile.IMAGE
    image: str = ""
    gpu_type: str = ""
    dataset_repo: str = ""
    detach: bool = True


RuntimeTarget = Annotated[DockerTarget | SshTarget | TargonTarget, Field(discriminator="runtime_name")]


class DockerRunMetadata(FrozenModel):
    runtime_name: Literal["docker"] = "docker"
    container_name: str
    image: str
    detach: bool
    profile: str = ""


class SshRunMetadata(FrozenModel):
    runtime_name: Literal["ssh"] = "ssh"
    session: str
    workspace: str
    host: str = ""
    target: str = ""
    profile: str = ""


class TargonRunMetadata(FrozenModel):
    runtime_name: Literal["targon"] = "targon"
    profile: str = ""
    image: str = ""
    dataset_repo: str = ""
    artifact_name: str = ""
    bundle_name: str = ""
    project_name: str = ""
    url: str = ""


RunMetadata = Annotated[DockerRunMetadata | SshRunMetadata | TargonRunMetadata, Field(discriminator="runtime_name")]


class RunHandle(FrozenModel):
    runtime_kind: str
    run_id: str
    target_id: str
    submitted_at: float = Field(default_factory=time.time)
    bundle_path: str = ""
    metadata: RunMetadata | None = None


class RunStatus(FrozenModel):
    runtime_kind: str
    run_id: str
    state: RunState
    detail: str = ""
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ArtifactManifest(FrozenModel):
    logs: dict[str, str] = Field(default_factory=dict)
    artifacts: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class RenderBundleRequest(FrozenModel):
    bundle_path: str
    job: JobSpec
    overwrite: bool = False
    context: RequestContext = Field(default_factory=RequestContext)


class RunBundleRequest(FrozenModel):
    bundle_path: str
    target: RuntimeTarget
    context: RequestContext = Field(default_factory=RequestContext)


class RunStatusRequest(FrozenModel):
    handle: RunHandle
    context: RequestContext = Field(default_factory=RequestContext)


class RunLogsRequest(FrozenModel):
    handle: RunHandle
    tail: int = 100
    context: RequestContext = Field(default_factory=RequestContext)


class CollectArtifactsRequest(FrozenModel):
    handle: RunHandle
    context: RequestContext = Field(default_factory=RequestContext)


class TerminateRunRequest(FrozenModel):
    handle: RunHandle
    context: RequestContext = Field(default_factory=RequestContext)


@runtime_checkable
class RuntimeBackend(Protocol):
    async def run(self, request: RunBundleRequest) -> RunHandle:
        ...

    async def status(self, request: RunStatusRequest) -> RunStatus:
        ...

    async def logs(self, request: RunLogsRequest) -> str:
        ...

    async def collect(self, request: CollectArtifactsRequest) -> ArtifactManifest:
        ...

    async def terminate(self, request: TerminateRunRequest) -> None:
        ...


def json_safe_dump(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: json_safe_dump(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe_dump(item) for item in value]
    return value
