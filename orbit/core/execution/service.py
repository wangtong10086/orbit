"""Execution service that routes generic execution requests to concrete backends."""

from __future__ import annotations

from orbit.config import OrbitConfig
from orbit.core.contracts.execution import (
    CollectArtifactsRequest,
    ExecutionRequest,
    RunHandle,
    RunLogsRequest,
    RunStatus,
    RunStatusRequest,
    TerminateRunRequest,
    backend_key_for_request,
)
from orbit.core.execution.backends.local_docker import LocalDockerRuntime
from orbit.core.execution.backends.local_host import LocalHostProcessRuntime
from orbit.core.execution.backends.targon_rental_docker import TargonRentalDockerRuntime
from orbit.core.execution.backends.targon_rental_host import TargonRentalHostProcessRuntime


class ExecutionService:
    def __init__(self, config: OrbitConfig):
        self.config = config
        self.backends = {
            "local_host_process": LocalHostProcessRuntime(config),
            "local_docker_image": LocalDockerRuntime(config),
            "targon_rental_docker_image": TargonRentalDockerRuntime(config),
            "targon_rental_host_process": TargonRentalHostProcessRuntime(config),
        }

    async def run(self, request: ExecutionRequest) -> RunHandle:
        backend = self.backends.get(backend_key_for_request(request))
        if backend is None:
            raise ValueError(
                f"Unsupported execution path: {request.placement.kind.value} + {request.launch_mode.kind.value}"
            )
        return await backend.run(request)

    async def status(self, request: RunStatusRequest) -> RunStatus:
        return await self._backend_for_handle(request.handle).status(request)

    async def logs(self, request: RunLogsRequest) -> str:
        return await self._backend_for_handle(request.handle).logs(request)

    async def collect(self, request: CollectArtifactsRequest):
        return await self._backend_for_handle(request.handle).collect(request)

    async def terminate(self, request: TerminateRunRequest) -> None:
        await self._backend_for_handle(request.handle).terminate(request)

    def _backend_for_handle(self, handle: RunHandle):
        backend = self.backends.get(handle.runtime_kind)
        if backend is None:
            raise ValueError(f"Unknown runtime backend for handle: {handle.runtime_kind}")
        return backend
