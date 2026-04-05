"""Base types and protocol for compute backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
import time

from pydantic import Field

from orbit.foundation.schema import StrictModel


class GpuInstance(StrictModel):
    """A provisioned GPU instance, backend-agnostic."""

    id: str
    backend: str
    gpu_type: str
    status: str
    created_at: float = Field(default_factory=time.time)

    host: str | None = None
    port: int = 22
    user: str = "root"
    url: str | None = None

    gpu_count: int = 1
    cost_per_hour: float = 0.0
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ProvisionRequest(StrictModel):
    backend: str = "targon"
    gpu_type: str = "H200"
    name: str = "affine-train"
    host: str = ""
    port: int = 22
    user: str = "root"
    key: str = ""
    image: str = "wangtong123/orbit:latest"
    command: list[str] | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    service_port: int = 8080
    min_replicas: int = 1


@runtime_checkable
class ComputeBackend(Protocol):
    async def provision(self, request: ProvisionRequest) -> GpuInstance:
        ...

    async def terminate(self, instance: GpuInstance) -> None:
        ...

    async def list_instances(self) -> list[GpuInstance]:
        ...

    async def health_check(self, instance: GpuInstance) -> dict:
        ...

    async def exec(self, instance: GpuInstance, command: str, timeout: int = 60) -> tuple[int, str, str]:
        ...

    async def upload(self, instance: GpuInstance, local_path: str, remote_path: str) -> None:
        ...

    async def download(self, instance: GpuInstance, remote_path: str, local_path: str) -> None:
        ...
