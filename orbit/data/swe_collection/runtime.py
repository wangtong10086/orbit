"""Docker-backed SWE workspace runtime."""

from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import dataclass


SANITIZE_GIT = (
    "cd /app && "
    "git config user.email 'swe-agent@test.local' && "
    "git config user.name 'SWE Agent' && "
    "git checkout -- . >/dev/null 2>&1 || true && "
    "git clean -fd >/dev/null 2>&1 || true"
)


def _decode_tool_command(command: str | list[str]) -> str:
    if isinstance(command, str):
        return command
    if len(command) >= 3 and command[0] == "bash" and command[1] == "-lc":
        return command[2]
    return " ".join(command)


@dataclass
class SweExecResult:
    stdout: str
    stderr: str
    output: str
    returncode: int


class SweDockerWorkspace:
    """One isolated Docker workspace for a SWE task."""

    def __init__(self, *, container_name: str, image: str):
        self.container_name = container_name
        self.image = image

    def exec(self, command: str | list[str], *, timeout: int = 120, stdin_data: str | None = None) -> SweExecResult:
        decoded = _decode_tool_command(command)
        docker_cmd = ["docker", "exec"]
        if stdin_data is not None:
            docker_cmd.append("-i")
        docker_cmd.extend([self.container_name, "bash", "-lc", decoded])
        proc = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=stdin_data,
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        output = stdout
        if stderr:
            output = f"{output}\n{stderr}".strip() if output else stderr
        return SweExecResult(stdout=stdout, stderr=stderr, output=output, returncode=proc.returncode)

    def sanitize(self) -> None:
        self.exec(SANITIZE_GIT, timeout=60)

    def changed_files(self) -> list[str]:
        result = self.exec("cd /app && git diff --name-only && git diff --cached --name-only", timeout=30)
        files = [line.strip() for line in result.output.splitlines() if line.strip()]
        deduped: list[str] = []
        seen: set[str] = set()
        for path in files:
            if path not in seen:
                seen.add(path)
                deduped.append(path)
        return deduped

    def diff_patch(self) -> str:
        result = self.exec("cd /app && (git diff --cached; git diff)", timeout=60)
        return result.output

    def git_status_short(self) -> str:
        result = self.exec("cd /app && git status --short", timeout=30)
        return result.output

    def has_patch(self) -> bool:
        return bool(self.diff_patch().strip())

    def close(self) -> None:
        try:
            subprocess.run(
                ["docker", "rm", "-f", self.container_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
            )
        except subprocess.TimeoutExpired:
            try:
                subprocess.run(
                    ["docker", "kill", self.container_name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                pass
            subprocess.run(
                ["docker", "rm", "-f", self.container_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )


class SweDockerWorkspaceRuntime:
    """Provision Docker workspaces for SWE tasks."""

    def __init__(self, *, memory: str = "4g"):
        self.memory = memory

    def resolve_image(self, task: dict) -> str:
        raw = str(task.get("dockerhub_tag", "")).strip()
        if not raw:
            raise ValueError("task missing dockerhub_tag")
        if "/" in raw and ":" in raw:
            return raw
        if ":" in raw:
            return f"affinefoundation/swe_infinite_images:{raw.split(':', 1)[1]}"
        return f"affinefoundation/swe_infinite_images:{raw}"

    def create_workspace(self, task: dict) -> SweDockerWorkspace:
        image = self.resolve_image(task)
        inspect = subprocess.run(["docker", "image", "inspect", image], capture_output=True, text=True, timeout=10)
        if inspect.returncode != 0:
            pull = subprocess.run(["docker", "pull", image], capture_output=True, text=True, timeout=300)
            if pull.returncode != 0:
                raise RuntimeError(f"docker pull failed for {image}: {(pull.stderr or pull.stdout).strip()}")
        name = f"orbit-swe-{uuid.uuid4().hex[:12]}"
        run = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "--memory",
                self.memory,
                "--workdir",
                "/app",
                "--entrypoint",
                "",
                image,
                "sleep",
                "1800",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if run.returncode != 0:
            raise RuntimeError(f"docker run failed: {(run.stderr or run.stdout).strip()}")
        workspace = SweDockerWorkspace(container_name=name, image=image)
        workspace.sanitize()
        return workspace

    def probe_workspace(self, task: dict) -> tuple[bool, str]:
        workspace = None
        try:
            workspace = self.create_workspace(task)
            result = workspace.exec("cd /app && pwd && git status --short >/dev/null", timeout=60)
            if result.returncode != 0:
                return False, (result.output or "docker exec probe failed").strip()
            return True, "ok"
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"
        finally:
            if workspace is not None:
                workspace.close()


def encode_tool_observation(output: str, returncode: int) -> str:
    return json.dumps(
        {
            "output": output,
            "metadata": {
                "exit_code": returncode,
                "duration_seconds": 0.0,
            },
        },
        ensure_ascii=False,
    )
