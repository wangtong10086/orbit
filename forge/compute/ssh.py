"""SSH-based compute backend for pre-provisioned machines."""

import json
import subprocess
import os
from typing import Optional

from forge.compute.base import GpuInstance


class SshBackend:
    """SSH/SCP backend for manually provisioned machines."""

    def __init__(self, machines_file: str):
        self.machines_file = machines_file

    def _load_machines(self) -> list[dict]:
        if os.path.exists(self.machines_file):
            with open(self.machines_file) as f:
                return json.load(f).get("machines", [])
        return []

    def _save_machines(self, machines: list[dict]):
        with open(self.machines_file, "w") as f:
            json.dump({"machines": machines}, f, indent=2)

    def _ssh_cmd(self, instance: GpuInstance) -> list[str]:
        cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
        ]
        if instance.port != 22:
            cmd.extend(["-p", str(instance.port)])
        key = instance.metadata.get("key")
        if key:
            cmd.extend(["-i", key])
        cmd.append(f"{instance.user}@{instance.host}")
        return cmd

    def _scp_cmd(self, instance: GpuInstance) -> list[str]:
        cmd = ["scp", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10"]
        if instance.port != 22:
            cmd.extend(["-P", str(instance.port)])
        key = instance.metadata.get("key")
        if key:
            cmd.extend(["-i", key])
        return cmd

    async def provision(self, gpu_type: str = "H200", **kwargs) -> GpuInstance:
        """Register an existing machine. Expects host/port/user in kwargs."""
        host = kwargs.get("host")
        if not host:
            raise ValueError("SSH backend requires 'host' parameter")

        name = kwargs.get("name", host)
        port = kwargs.get("port", 22)
        user = kwargs.get("user", "root")
        key = kwargs.get("key", "")

        instance = GpuInstance(
            id=name,
            backend="ssh",
            gpu_type=gpu_type,
            status="ready",
            host=host,
            port=port,
            user=user,
            metadata={"name": name, "key": key},
        )

        # Save to machines.json
        machines = self._load_machines()
        machine_entry = {"name": name, "host": host, "port": port, "user": user}
        if key:
            machine_entry["key"] = key

        # Update or append
        found = False
        for i, m in enumerate(machines):
            if m.get("name") == name or m.get("host") == host:
                machines[i] = machine_entry
                found = True
                break
        if not found:
            machines.append(machine_entry)

        self._save_machines(machines)
        return instance

    async def terminate(self, instance: GpuInstance) -> None:
        """Remove machine from registry (doesn't actually terminate)."""
        machines = self._load_machines()
        machines = [m for m in machines if m.get("name") != instance.id and m.get("host") != instance.host]
        self._save_machines(machines)

    async def list_instances(self) -> list[GpuInstance]:
        """List registered machines."""
        machines = self._load_machines()
        instances = []
        for m in machines:
            instances.append(GpuInstance(
                id=m.get("name", m["host"]),
                backend="ssh",
                gpu_type="unknown",
                status="unknown",
                host=m["host"],
                port=m.get("port", 22),
                user=m.get("user", "root"),
                metadata=m,
            ))
        return instances

    async def health_check(self, instance: GpuInstance) -> dict:
        """Check machine health via SSH."""
        result = {"id": instance.id, "host": instance.host}

        try:
            rc, stdout, stderr = await self.exec(
                instance,
                "echo OK && nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader 2>/dev/null || echo 'NO_GPU'",
                timeout=15,
            )

            if rc == 0:
                lines = stdout.strip().split("\n")
                result["status"] = "online"
                if len(lines) > 1 and lines[1] != "NO_GPU":
                    result["gpu_info"] = lines[1:]
                else:
                    result["gpu_info"] = ["No GPU detected"]

                # Disk space
                rc2, out2, _ = await self.exec(instance, "df -h / | tail -1 | awk '{print $4}'", timeout=10)
                if rc2 == 0:
                    result["disk_free"] = out2.strip()

                # Training status
                rc3, out3, _ = await self.exec(
                    instance, "pgrep -a 'python.*train' 2>/dev/null | head -3 || echo 'no_training'", timeout=10
                )
                if rc3 == 0:
                    output = out3.strip()
                    result["training"] = "running" if output != "no_training" else "idle"

                # Latest checkpoint
                rc4, out4, _ = await self.exec(
                    instance, "ls -td /root/checkpoints/*/ 2>/dev/null | head -1 || echo 'none'", timeout=10
                )
                if rc4 == 0:
                    result["latest_checkpoint"] = out4.strip()
            else:
                result["status"] = "unreachable"
                result["error"] = stderr[:200]

        except subprocess.TimeoutExpired:
            result["status"] = "timeout"
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)[:200]

        return result

    async def exec(self, instance: GpuInstance, command: str, timeout: int = 60) -> tuple[int, str, str]:
        """Execute command via SSH."""
        cmd = self._ssh_cmd(instance) + [command]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr

    async def upload(self, instance: GpuInstance, local_path: str, remote_path: str) -> None:
        """Upload file via SCP."""
        cmd = self._scp_cmd(instance)
        cmd.extend(["-r", local_path, f"{instance.user}@{instance.host}:{remote_path}"])
        subprocess.run(cmd, check=True)

    async def download(self, instance: GpuInstance, remote_path: str, local_path: str) -> None:
        """Download file via SCP/rsync."""
        cmd = [
            "rsync", "-avz", "--progress",
            "-e", f"ssh -p {instance.port} -o StrictHostKeyChecking=no",
            f"{instance.user}@{instance.host}:{remote_path}",
            local_path,
        ]
        subprocess.run(cmd, check=True)
