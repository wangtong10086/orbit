"""Compute manager - orchestrates multiple backends."""

from typing import Optional

from forge.config import ForgeConfig
from forge.compute.base import ComputeBackend, GpuInstance, ProvisionRequest


class ComputeManager:
    """High-level compute orchestrator across backends."""

    def __init__(self, config: ForgeConfig):
        self.config = config
        self.backends: dict[str, ComputeBackend] = {}
        self._init_backends()

    def _init_backends(self):
        """Initialize available backends."""
        # SSH backend (always available)
        from forge.compute.ssh import SshBackend
        self.backends["ssh"] = SshBackend(str(self.config.machines_file))

    def get_backend(self, name: str) -> ComputeBackend:
        """Get a specific backend."""
        if name not in self.backends:
            available = ", ".join(self.backends.keys())
            raise ValueError(f"Backend '{name}' not available. Available: {available}")
        return self.backends[name]

    async def provision(self, request: ProvisionRequest) -> GpuInstance:
        """Provision a GPU instance using the specified backend."""
        be = self.get_backend(request.backend)
        return await be.provision(request)

    async def terminate(self, instance: GpuInstance) -> None:
        """Terminate an instance using its original backend."""
        be = self.get_backend(instance.backend)
        await be.terminate(instance)

    async def list_all(self) -> list[GpuInstance]:
        """List instances across all backends."""
        all_instances = []
        for name, be in self.backends.items():
            try:
                instances = await be.list_instances()
                all_instances.extend(instances)
            except Exception:
                pass
        return all_instances

    async def health_check(self, instance: GpuInstance) -> dict:
        """Health check an instance."""
        be = self.get_backend(instance.backend)
        return await be.health_check(instance)

    async def exec(self, instance: GpuInstance, command: str, timeout: int = 60) -> tuple[int, str, str]:
        """Execute command on an instance."""
        be = self.get_backend(instance.backend)
        return await be.exec(instance, command, timeout)

    async def capacity(self) -> dict:
        """Capacity reporting is not available in rental-only mode."""
        return {}
