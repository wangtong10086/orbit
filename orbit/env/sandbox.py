"""Sandbox API — runtime configuration and lifecycle management.

Analogous to ROCK's Sandbox SDK: manages isolated execution environments
for running evaluations. Separated from the GEM protocol (env interaction).

Usage:
    config = SandboxConfig(image="python:3.11", memory="8g", cpus=2.0)
    sandbox = Sandbox(config)
    await sandbox.start()
    result = await sandbox.execute("python eval.py")
    await sandbox.stop()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SandboxStatus(Enum):
    """Sandbox lifecycle states."""
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class SandboxConfig:
    """Configuration for a sandboxed execution environment.

    Analogous to ROCK's SandboxConfig — defines resource limits
    and runtime settings for an isolated environment container.
    """
    image: str = "python:3.11"
    memory: str = "8g"
    cpus: float = 2.0
    gpu: str = ""
    timeout: int = 300
    env_vars: dict[str, str] = field(default_factory=dict)
    working_dir: str = "/workspace"
    network_enabled: bool = True


@dataclass
class ExecutionResult:
    """Result of executing a command in a sandbox."""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False


class Sandbox:
    """Sandbox runtime — manages an isolated execution environment.

    Analogous to ROCK's Sandbox class. Provides lifecycle management
    (start/stop) and command execution within an isolated container.

    This is the infrastructure layer — separated from the GEM protocol
    which handles environment interaction logic.
    """

    def __init__(self, config: Optional[SandboxConfig] = None):
        self._config = config or SandboxConfig()
        self._status = SandboxStatus.CREATED
        self._sandbox_id: Optional[str] = None

    @property
    def config(self) -> SandboxConfig:
        return self._config

    @property
    def status(self) -> SandboxStatus:
        return self._status

    @property
    def sandbox_id(self) -> Optional[str]:
        return self._sandbox_id

    async def start(self) -> None:
        """Provision and start the sandbox environment.

        In a full implementation, this would create a Docker container
        or remote VM with the specified config.
        """
        self._status = SandboxStatus.STARTING
        # Placeholder: actual provisioning goes via orbit.compute backends
        import hashlib
        import time
        self._sandbox_id = hashlib.md5(
            f"{self._config.image}-{time.time()}".encode()
        ).hexdigest()[:12]
        self._status = SandboxStatus.RUNNING

    async def execute(self, cmd: str, timeout: Optional[int] = None) -> ExecutionResult:
        """Execute a command inside the sandbox.

        Args:
            cmd: Shell command to run
            timeout: Override default timeout (seconds)

        Returns:
            ExecutionResult with stdout/stderr/exit_code
        """
        if self._status != SandboxStatus.RUNNING:
            raise RuntimeError(f"Sandbox not running (status={self._status.value})")
        # Placeholder: actual execution via SSH/Docker exec
        return ExecutionResult(stdout="", stderr="", exit_code=0)

    async def stop(self) -> None:
        """Stop and clean up the sandbox."""
        self._status = SandboxStatus.STOPPING
        self._status = SandboxStatus.STOPPED

    def is_alive(self) -> bool:
        """Check if sandbox is in a running state."""
        return self._status == SandboxStatus.RUNNING
