"""Stable execution-plane contracts."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
import time
from typing import Annotated, Literal, Protocol, runtime_checkable

from pydantic import Field, StringConstraints

from forge.foundation.schema import FrozenModel, JsonValue, RequestContext


EnvKey = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_-]*$")]


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


class PlacementKind(str, Enum):
    LOCAL = "local"
    TARGON_RENTAL = "targon_rental"


class LaunchModeKind(str, Enum):
    HOST_PROCESS = "host_process"
    DOCKER_IMAGE = "docker_image"


class ResourceRequest(FrozenModel):
    gpu_type: str = "unknown"
    gpu_count: int = 1
    cpu_count: int = 0
    memory_gb: int = 0


class InputRef(FrozenModel):
    name: str
    relative_path: str
    required: bool = True


class OutputRef(FrozenModel):
    name: str
    relative_path: str
    kind: str = "file"


class JobSpec(FrozenModel):
    job_id: str
    kind: JobKind
    resources: ResourceRequest = Field(default_factory=ResourceRequest)
    runtime_env: dict[EnvKey, str] = Field(default_factory=dict)
    inputs: tuple[InputRef, ...] = Field(default_factory=tuple)
    expected_outputs: tuple[OutputRef, ...] = Field(default_factory=tuple)
    entrypoint: str = "scripts/entrypoint.sh"
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class PlacementSpec(FrozenModel):
    kind: PlacementKind
    target: str = ""


class LaunchModeSpec(FrozenModel):
    kind: LaunchModeKind
    image: str = ""
    detach: bool = True


class ExecutionRequest(FrozenModel):
    bundle_path: str
    placement: PlacementSpec
    launch_mode: LaunchModeSpec
    resources: ResourceRequest = Field(default_factory=ResourceRequest)
    runtime_env: dict[EnvKey, str] = Field(default_factory=dict)
    context: RequestContext = Field(default_factory=RequestContext)


class LocalHostRunMetadata(FrozenModel):
    runtime_name: Literal["local_host_process"] = "local_host_process"
    pid: int = 0
    detach: bool = True
    project_root: str = ""
    bundle_root: str = ""
    entrypoint: str = "scripts/entrypoint.sh"


class LocalDockerRunMetadata(FrozenModel):
    runtime_name: Literal["local_docker_image"] = "local_docker_image"
    container_name: str
    image: str
    detach: bool


class TargonRentalDockerRunMetadata(FrozenModel):
    runtime_name: Literal["targon_rental_docker_image"] = "targon_rental_docker_image"
    target: str = ""
    host: str = ""
    workspace: str = ""
    container_name: str = ""
    image: str = ""
    staging_repo: str = ""
    project_archive_path: str = ""
    bundle_archive_path: str = ""


class TargonRentalHostRunMetadata(FrozenModel):
    runtime_name: Literal["targon_rental_host_process"] = "targon_rental_host_process"
    target: str = ""
    host: str = ""
    workspace: str = ""
    pid: int = 0
    detach: bool = True
    entrypoint: str = "scripts/entrypoint.sh"


RunMetadata = Annotated[
    LocalHostRunMetadata | LocalDockerRunMetadata | TargonRentalDockerRunMetadata | TargonRentalHostRunMetadata,
    Field(discriminator="runtime_name"),
]


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
class ExecutionBackend(Protocol):
    async def run(self, request: ExecutionRequest) -> RunHandle:
        ...

    async def status(self, request: RunStatusRequest) -> RunStatus:
        ...

    async def logs(self, request: RunLogsRequest) -> str:
        ...

    async def collect(self, request: CollectArtifactsRequest) -> ArtifactManifest:
        ...

    async def terminate(self, request: TerminateRunRequest) -> None:
        ...


def backend_key_for_request(request: ExecutionRequest) -> str:
    return f"{request.placement.kind.value}_{request.launch_mode.kind.value}"


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
