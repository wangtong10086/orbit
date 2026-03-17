"""Base types and protocol for compute backends."""

from dataclasses import dataclass, field
from typing import Protocol, Optional, runtime_checkable
import time


@dataclass
class GpuInstance:
    """A provisioned GPU instance, backend-agnostic."""

    id: str
    backend: str  # "targon" or "ssh"
    gpu_type: str  # "H100", "H200", etc.
    status: str  # "provisioning", "ready", "training", "dead"
    created_at: float = field(default_factory=time.time)

    # Connection info (backend-specific)
    host: Optional[str] = None
    port: int = 22
    user: str = "root"
    url: Optional[str] = None  # For Targon serverless containers

    # Resource details
    gpu_count: int = 1
    cost_per_hour: float = 0.0

    # Backend-specific metadata
    metadata: dict = field(default_factory=dict)


@runtime_checkable
class ComputeBackend(Protocol):
    """Protocol for compute backends."""

    async def provision(self, gpu_type: str = "H200", **kwargs) -> GpuInstance:
        """Provision a new GPU instance."""
        ...

    async def terminate(self, instance: GpuInstance) -> None:
        """Terminate an instance."""
        ...

    async def list_instances(self) -> list[GpuInstance]:
        """List all active instances."""
        ...

    async def health_check(self, instance: GpuInstance) -> dict:
        """Check instance health."""
        ...

    async def exec(self, instance: GpuInstance, command: str, timeout: int = 60) -> tuple[int, str, str]:
        """Execute command on instance. Returns (returncode, stdout, stderr)."""
        ...

    async def upload(self, instance: GpuInstance, local_path: str, remote_path: str) -> None:
        """Upload file to instance."""
        ...

    async def download(self, instance: GpuInstance, remote_path: str, local_path: str) -> None:
        """Download file from instance."""
        ...
