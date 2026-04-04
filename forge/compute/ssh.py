"""SSH-based compute backend for pre-provisioned machines."""

import json
import pathlib
import subprocess
import os
import shlex
import tempfile
from typing import Optional

from forge.compute.base import GpuInstance, ProvisionRequest


class SshBackend:
    """SSH/SCP backend for manually provisioned machines."""

    CONNECT_TIMEOUT_SECONDS = 60
    _TAR_STREAM_SENTINEL = b"__AFFINE_TAR_BEGIN__\n"

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
            "-o", f"ConnectTimeout={self.CONNECT_TIMEOUT_SECONDS}",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
        ]
        if instance.port != 22:
            cmd.extend(["-p", str(instance.port)])
        key = instance.metadata.get("key")
        if key:
            cmd.extend(["-i", os.path.expanduser(key)])
        cmd.append(f"{instance.user}@{instance.host}")
        return cmd

    def _addr(self, instance: GpuInstance) -> str:
        return f"{instance.user}@{instance.host}"

    def _filter_banner(self, text: str) -> str:
        return "\n".join(
            line for line in (text or "").splitlines()
            if not line.startswith("Connecting to container")
        ).strip()

    @classmethod
    def _write_after_sentinel(cls, source, output) -> bool:
        """Copy bytes from source to output after a sentinel line appears."""
        buffer = b""
        found = False
        keep = max(len(cls._TAR_STREAM_SENTINEL) - 1, 0)
        while True:
            chunk = source.read(64 * 1024)
            if not chunk:
                break
            if found:
                output.write(chunk)
                continue
            buffer += chunk
            idx = buffer.find(cls._TAR_STREAM_SENTINEL)
            if idx == -1:
                if keep:
                    buffer = buffer[-keep:]
                else:
                    buffer = b""
                continue
            found = True
            output.write(buffer[idx + len(cls._TAR_STREAM_SENTINEL):])
            buffer = b""
        return found

    async def provision(self, request: ProvisionRequest) -> GpuInstance:
        """Register an existing machine."""
        host = request.host
        if not host:
            raise ValueError("SSH backend requires 'host' parameter")

        name = request.name or host
        port = request.port
        user = request.user
        key = request.key

        instance = GpuInstance(
            id=name,
            backend="ssh",
            gpu_type=request.gpu_type,
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
        return proc.returncode, self._filter_banner(proc.stdout), self._filter_banner(proc.stderr)

    def _rsync_cmd(self, instance: GpuInstance) -> list[str]:
        ssh_opts = f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10"
        if instance.port != 22:
            ssh_opts += f" -p {instance.port}"
        key = instance.metadata.get("key")
        if key:
            ssh_opts += f" -i {os.path.expanduser(key)}"
        return ["rsync", "-az", "--progress", "-e", ssh_opts]

    def _scp_cmd(self, instance: GpuInstance) -> list[str]:
        """SCP fallback when rsync unavailable."""
        cmd = ["scp", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10", "-r"]
        if instance.port != 22:
            cmd.extend(["-P", str(instance.port)])
        key = instance.metadata.get("key")
        if key:
            cmd.extend(["-i", os.path.expanduser(key)])
        return cmd

    def _transfer_cmd(self, instance: GpuInstance, local_path: str, remote_path: str, upload: bool) -> list[str]:
        """Build rsync (preferred) or scp command."""
        import shutil
        remote = f"{instance.user}@{instance.host}:{remote_path}"
        if shutil.which("rsync"):
            cmd = self._rsync_cmd(instance)
            return cmd + ([local_path, remote] if upload else [remote, local_path])
        cmd = self._scp_cmd(instance)
        return cmd + ([local_path, remote] if upload else [remote, local_path])

    def _upload_via_tar(self, instance: GpuInstance, local_path: str, remote_path: str) -> None:
        """Fallback upload path that can handle directories on bannered SSH hosts."""
        local = pathlib.Path(local_path)
        if not local.exists():
            raise FileNotFoundError(local_path)

        if local.is_file():
            ssh_cmd = self._ssh_cmd(instance) + [f"cat > {shlex.quote(remote_path)}"]
            with open(local, "rb") as handle:
                subprocess.run(ssh_cmd, stdin=handle, check=True, timeout=3600)
            return

        remote_target = remote_path.rstrip("/")
        remote_parent = os.path.dirname(remote_target) or "."
        remote_name = os.path.basename(remote_target)
        local_parent = str(local.parent)
        local_name = local.name
        extracted_path = os.path.join(remote_parent, local_name)
        rename_cmd = ""
        if local_name != remote_name:
            rename_cmd = (
                f" && rm -rf {shlex.quote(remote_target)}"
                f" && mv {shlex.quote(extracted_path)} {shlex.quote(remote_target)}"
            )
        remote_cmd = (
            f"mkdir -p {shlex.quote(remote_parent)}"
            f" && tar -xf - -C {shlex.quote(remote_parent)}"
            f"{rename_cmd}"
        )

        tar_proc = subprocess.Popen(
            ["tar", "-C", local_parent, "-cf", "-", local_name],
            stdout=subprocess.PIPE,
        )
        try:
            ssh_proc = subprocess.Popen(
                self._ssh_cmd(instance) + [remote_cmd],
                stdin=tar_proc.stdout,
            )
            assert tar_proc.stdout is not None
            tar_proc.stdout.close()
            ssh_rc = ssh_proc.wait(timeout=3600)
            tar_rc = tar_proc.wait(timeout=3600)
        finally:
            if tar_proc.stdout is not None:
                tar_proc.stdout.close()

        if tar_rc != 0 or ssh_rc != 0:
            raise RuntimeError(
                f"tar-over-ssh upload failed for {local_path} -> {remote_path} "
                f"(tar_rc={tar_rc}, ssh_rc={ssh_rc})"
            )

    def _download_via_tar(self, instance: GpuInstance, remote_path: str, local_path: str) -> None:
        """Fallback download path that can handle bannered SSH hosts."""
        local = pathlib.Path(local_path)
        local.mkdir(parents=True, exist_ok=True)
        remote = remote_path.rstrip("/")
        remote_parent = os.path.dirname(remote) or "."
        remote_name = os.path.basename(remote)
        sentinel = self._TAR_STREAM_SENTINEL.decode("ascii").strip()
        remote_cmd = (
            f"printf '%s\\n' {shlex.quote(sentinel)} && "
            f"tar -cf - -C {shlex.quote(remote_parent)} {shlex.quote(remote_name)}"
        )
        tar_proc = subprocess.Popen(
            self._ssh_cmd(instance) + [remote_cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            assert tar_proc.stdout is not None
            with tempfile.NamedTemporaryFile(suffix=".tar") as archive:
                found = self._write_after_sentinel(tar_proc.stdout, archive)
                archive.flush()
                stderr = tar_proc.stderr.read().decode("utf-8", errors="replace") if tar_proc.stderr is not None else ""
                tar_rc = tar_proc.wait(timeout=3600)
                if tar_rc != 0:
                    raise RuntimeError(
                        f"tar-over-ssh download failed for {remote_path} -> {local_path} "
                        f"(tar_rc={tar_rc}, stderr={self._filter_banner(stderr) or 'empty'})"
                    )
                if not found:
                    raise RuntimeError(
                        f"tar-over-ssh download failed for {remote_path} -> {local_path} "
                        "(missing tar stream sentinel)"
                    )
                subprocess.run(["tar", "-xf", archive.name, "-C", str(local)], check=True, timeout=3600)
        finally:
            if tar_proc.stdout is not None:
                tar_proc.stdout.close()
            if tar_proc.stderr is not None:
                tar_proc.stderr.close()

    async def upload(self, instance: GpuInstance, local_path: str, remote_path: str) -> None:
        """Upload file/dir via rsync, scp, or ssh pipe fallback.

        Targon SSH deployments output a banner on non-interactive sessions,
        breaking the rsync/scp protocol. We fall back to piping via ssh.
        """
        try:
            subprocess.run(self._transfer_cmd(instance, local_path, remote_path, upload=True),
                           check=True, timeout=3600, capture_output=True)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            try:
                remote = f"{instance.user}@{instance.host}:{remote_path}"
                cmd = self._scp_cmd(instance) + [local_path, remote]
                subprocess.run(cmd, check=True, timeout=3600, capture_output=True)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                self._upload_via_tar(instance, local_path, remote_path)

    async def download(self, instance: GpuInstance, remote_path: str, local_path: str) -> None:
        """Download file/dir via rsync, scp, or ssh pipe fallback."""
        try:
            subprocess.run(
                self._transfer_cmd(instance, local_path, remote_path, upload=False),
                check=True,
                timeout=3600,
                capture_output=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            self._download_via_tar(instance, remote_path, local_path)
