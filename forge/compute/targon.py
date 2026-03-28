"""Targon compute backend.

Uses targon-sdk (pip install targon-sdk) to provision GPU containers
via Targon's serverless API and manage lifecycle.
"""

from typing import AsyncGenerator, Optional

from forge.compute.base import GpuInstance

# Map our GPU aliases to targon-sdk resource tier names
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
    "B200-M": "b200-medium",
    "B200-L": "b200-large",
    "B200-XL": "b200-xlarge",
    "RTX4090": "rtx4090-small",
    "RTX4090-M": "rtx4090-medium",
    "RTX4090-L": "rtx4090-large",
    "RTX6000B": "rtx6000b-small",
}


class TargonBackend:
    """Targon serverless container backend using targon-sdk."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _new_client(self):
        """Create a fresh Client for each operation."""
        from targon import Client
        return Client(api_key=self.api_key)

    async def capacity(self) -> list[dict]:
        """Get available compute capacity."""
        client = self._new_client()
        try:
            caps = await client.async_inventory.capacity()
            return [
                {
                    "name": c.name,
                    "available": c.available,
                    "cost_per_hour": c.cost_per_hour,
                    "gpu": c.gpu,
                }
                for c in caps
            ]
        finally:
            await client.aclose()

    async def provision(
        self,
        gpu_type: str = "H200",
        name: str = "affine-train",
        image: str = "wangtong123/affine-forge:latest",
        command: Optional[list[str]] = None,
        args: Optional[list[str]] = None,
        env: Optional[dict[str, str]] = None,
        port: int = 8080,
        min_replicas: int = 1,
        **kwargs,
    ) -> GpuInstance:
        """Provision a new Targon container with GPU.

        Uses AutoScalingConfig with min_replicas to prevent Knative scale-to-zero.
        """
        from targon.client.serverless import (
            AutoScalingConfig, ContainerConfig, CreateServerlessResourceRequest,
            EnvVar, NetworkConfig, PortConfig,
        )

        resource = GPU_RESOURCE_MAP.get(gpu_type, gpu_type)
        client = self._new_client()

        env_vars = [EnvVar(name=k, value=v) for k, v in (env or {}).items()]
        container = ContainerConfig(
            image=image,
            command=command,
            args=args,
            env=env_vars,
        )
        network = NetworkConfig(port=PortConfig(port=port))
        scaling = AutoScalingConfig(min_replicas=min_replicas, max_replicas=max(min_replicas, 1))

        req = CreateServerlessResourceRequest(
            name=name,
            container=container,
            resource_name=resource,
            network=network,
            scaling=scaling,
        )

        try:
            result = await client.async_serverless.deploy_container(request=req)
        finally:
            await client.aclose()

        return GpuInstance(
            id=result.uid,
            backend="targon",
            gpu_type=gpu_type,
            status="provisioning",
            url=result.url,
            cost_per_hour=result.cost_per_hour if hasattr(result, "cost_per_hour") else 0.0,
            metadata={"name": result.name, "resource": resource},
        )

    async def terminate(self, instance: GpuInstance) -> None:
        """Delete a Targon serverless container."""
        client = self._new_client()
        try:
            await client.async_serverless.delete_container(instance.id)
        finally:
            await client.aclose()
        instance.status = "terminated"

    async def list_instances(self) -> list[GpuInstance]:
        """List all active Targon containers."""
        client = self._new_client()
        try:
            containers = await client.async_serverless.list_container()
        finally:
            await client.aclose()

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

    async def health_check(self, instance: GpuInstance) -> dict:
        """Check container health via workload state API."""
        client = self._new_client()
        try:
            state = await client.async_serverless.get_state(instance.id)
            return {
                "status": state.status,
                "message": state.message,
                "ready_replicas": state.ready_replicas,
                "total_replicas": state.total_replicas,
                "uid": state.uid,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            await client.aclose()

    async def get_events(self, instance_id: str, limit: int = 20) -> list[dict]:
        """Get recent events for a workload."""
        client = self._new_client()
        try:
            resp = await client.async_serverless.get_events(instance_id, limit=limit)
            return [{"event": e} for e in (resp.events if hasattr(resp, "events") else [])]
        except Exception as e:
            return [{"error": str(e)}]
        finally:
            await client.aclose()

    async def logs(
        self, instance_id: str, follow: bool = True, max_lines: int = 0
    ) -> AsyncGenerator[str, None]:
        """Stream logs from a Targon container."""
        client = self._new_client()
        count = 0
        try:
            async for line in client.async_logs.stream_logs(instance_id, follow=follow):
                yield line
                count += 1
                if max_lines and count >= max_lines:
                    break
        finally:
            await client.aclose()

    async def logs_snapshot(self, instance_id: str, tail: int = 50) -> list[str]:
        """Get recent logs (non-streaming). Returns last N lines."""
        lines = []
        try:
            async for line in self.logs(instance_id, follow=False, max_lines=tail):
                lines.append(line)
        except Exception:
            pass
        return lines[-tail:] if len(lines) > tail else lines
