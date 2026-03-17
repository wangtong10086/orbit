"""Targon serverless compute backend.

Uses targon-sdk to provision GPU containers via Targon's serverless API.
"""

from typing import AsyncGenerator, Optional

from forge.compute.base import GpuInstance

GPU_RESOURCE_MAP = {
    "H200": "h200-small",
    "H200-M": "h200-medium",
    "H200-L": "h200-large",
    "H200-XL": "h200-xlarge",
    "H100": "h100-small",
    "H100-M": "h100-medium",
    "H100-L": "h100-large",
    "H100-XL": "h100-xlarge",
    "B200": "b200-small",
    "RTX4090": "rtx4090-small",
}


class TargonBackend:
    """Targon serverless container backend."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            from targon.client.client import Client
            self._client = Client(api_key=self.api_key)
        return self._client

    async def capacity(self) -> list[dict]:
        """Get available compute capacity."""
        client = self._get_client()
        async with client:
            caps = await client.async_inventory.capacity()
            return [{"name": c.name, "count": c.count} for c in caps]

    async def provision(
        self,
        gpu_type: str = "H200",
        name: str = "affine-train",
        image: str = "nvidia/cuda:12.4.0-devel-ubuntu22.04",
        command: Optional[list[str]] = None,
        args: Optional[list[str]] = None,
        env: Optional[dict[str, str]] = None,
        port: int = 8080,
        **kwargs,
    ) -> GpuInstance:
        """Provision a new Targon serverless container with GPU."""
        resource = GPU_RESOURCE_MAP.get(gpu_type, gpu_type)
        client = self._get_client()

        async with client:
            result = await client.async_serverless.deploy_container(
                name=name,
                image=image,
                resource=resource,
                command=command,
                args=args,
                env=env or {},
                port=port,
            )

        return GpuInstance(
            id=result.uid,
            backend="targon",
            gpu_type=gpu_type,
            status="provisioning",
            url=result.url,
            metadata={"name": result.name, "resource": resource},
        )

    async def terminate(self, instance: GpuInstance) -> None:
        """Delete a Targon serverless container."""
        client = self._get_client()
        async with client:
            await client.async_serverless.delete_container(instance.id)
        instance.status = "terminated"

    async def list_instances(self) -> list[GpuInstance]:
        """List all active Targon containers."""
        client = self._get_client()
        async with client:
            containers = await client.async_serverless.list_container()

        instances = []
        for c in containers:
            instances.append(GpuInstance(
                id=c.uid,
                backend="targon",
                gpu_type="unknown",
                status="ready",
                url=c.url,
                cost_per_hour=c.cost or 0.0,
                metadata={"name": c.name, "created_at": c.created_at},
            ))
        return instances

    async def logs(
        self, instance_id: str, follow: bool = True, max_lines: int = 0
    ) -> AsyncGenerator[str, None]:
        """Stream logs from a Targon container.

        Args:
            instance_id: Container UID
            follow: If True, keep streaming new logs
            max_lines: Stop after N lines (0=unlimited)
        """
        client = self._get_client()
        count = 0
        async with client:
            async for line in client.async_logs.stream_logs(instance_id, follow=follow):
                yield line
                count += 1
                if max_lines and count >= max_lines:
                    break

    async def logs_snapshot(self, instance_id: str, tail: int = 50) -> list[str]:
        """Get recent logs (non-streaming). Returns last N lines."""
        lines = []
        try:
            async for line in self.logs(instance_id, follow=False, max_lines=tail):
                lines.append(line)
        except Exception:
            pass
        return lines[-tail:] if len(lines) > tail else lines
