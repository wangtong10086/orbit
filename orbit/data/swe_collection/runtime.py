"""Docker-backed SWE workspace runtime."""

from __future__ import annotations

import json
import posixpath
import shlex
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from hashlib import sha256

from orbit.foundation.data_contracts import SweWorkspaceCheckpointV1


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

    def patch_hash(self) -> str:
        diff_patch = self.diff_patch()
        if not diff_patch.strip():
            return ""
        return sha256(diff_patch.encode("utf-8")).hexdigest()[:16]

    def capture_checkpoint(self, *, base_instance_id: str, parent_checkpoint_id: str = "") -> SweWorkspaceCheckpointV1:
        changed_files = tuple(self.changed_files())
        file_snapshots: dict[str, str] = {}
        for path in changed_files[:2]:
            try:
                file_snapshots[path] = self._copy_text_from_container(path)
            except (FileNotFoundError, ValueError):
                continue
        diff_patch = self.diff_patch()
        return SweWorkspaceCheckpointV1(
            checkpoint_id=f"{base_instance_id}-ckpt-{uuid.uuid4().hex[:8]}",
            base_instance_id=base_instance_id,
            parent_checkpoint_id=parent_checkpoint_id,
            changed_files=tuple(file_snapshots.keys()),
            patch_hash=self.patch_hash(),
            diff_patch=diff_patch,
            file_snapshots=file_snapshots,
            git_status_short=self.git_status_short(),
            metadata={
                "changed_file_count": len(changed_files),
            },
        )

    def restore_checkpoint(self, checkpoint: SweWorkspaceCheckpointV1) -> SweExecResult:
        started = time.time()
        try:
            self.sanitize()
            for path, text in checkpoint.file_snapshots.items():
                self._copy_text_to_container(path, text)
            restored_hash = self.patch_hash()
            if restored_hash != checkpoint.patch_hash:
                message = (
                    f"checkpoint restore hash mismatch: expected={checkpoint.patch_hash} got={restored_hash}"
                )
                return SweExecResult(stdout="", stderr=message, output=message, returncode=1)
            latency_ms = int((time.time() - started) * 1000)
            return SweExecResult(
                stdout=f"restored {checkpoint.checkpoint_id}",
                stderr="",
                output=f"restored {checkpoint.checkpoint_id} ({latency_ms} ms)",
                returncode=0,
            )
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            return SweExecResult(stdout="", stderr=message, output=message, returncode=1)

    def _workspace_relpath(self, path: str) -> str:
        raw = str(path or "").strip()
        if not raw or raw.startswith("/"):
            raise ValueError("path must be a non-empty relative workspace path")
        normalized = posixpath.normpath(f"/app/{raw}")
        if not normalized.startswith("/app/"):
            raise ValueError("path outside workspace")
        return normalized[len("/app/") :]

    def _copy_text_from_container(self, path: str) -> str:
        relpath = self._workspace_relpath(path)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as handle:
            local_path = handle.name
        try:
            proc = subprocess.run(
                ["docker", "cp", f"{self.container_name}:/app/{relpath}", local_path],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if proc.returncode != 0:
                raise FileNotFoundError((proc.stderr or proc.stdout).strip() or f"missing file: {path}")
            return open(local_path, encoding="utf-8", errors="replace").read()
        finally:
            subprocess.run(["rm", "-f", local_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    def _copy_text_to_container(self, path: str, text: str) -> None:
        relpath = self._workspace_relpath(path)
        parent = posixpath.dirname(relpath)
        if parent:
            mkdir = self.exec(f"mkdir -p {shlex.quote(posixpath.join('/app', parent))}", timeout=30)
            if mkdir.returncode != 0:
                raise RuntimeError(mkdir.output or f"failed to create parent dir for {path}")
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as handle:
            handle.write(text)
            local_path = handle.name
        try:
            proc = subprocess.run(
                ["docker", "cp", local_path, f"{self.container_name}:/app/{relpath}"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if proc.returncode != 0:
                raise RuntimeError((proc.stderr or proc.stdout).strip() or f"failed to write {path}")
        finally:
            subprocess.run(["rm", "-f", local_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    def read_context(
        self,
        path: str,
        *,
        focus_terms: tuple[str, ...] = (),
        max_lines: int = 220,
        window_radius: int = 40,
    ) -> str:
        try:
            text = self._copy_text_from_container(path)
        except (FileNotFoundError, ValueError):
            return ""
        lines = text.splitlines()
        start = 1
        end = min(len(lines), max_lines)
        for term in (term for term in focus_terms if term):
            for idx, line in enumerate(lines, start=1):
                if term in line:
                    start = max(1, idx - window_radius)
                    end = min(len(lines), idx + window_radius)
                    break
            else:
                continue
            break
        return "\n".join(f"{lineno:04d}: {lines[lineno - 1]}" for lineno in range(start, end + 1))

    def list_repo_files(self) -> tuple[str, ...]:
        result = self.exec("cd /app && git ls-files", timeout=60)
        if result.returncode != 0:
            return ()
        files = []
        seen: set[str] = set()
        for line in result.output.splitlines():
            path = line.strip()
            if path and path not in seen:
                seen.add(path)
                files.append(path)
        return tuple(files)

    def file_exists(self, path: str) -> bool:
        try:
            self._workspace_relpath(path)
        except ValueError:
            return False
        result = self.exec(f"test -f {shlex.quote(posixpath.join('/app', path))}", timeout=30)
        return result.returncode == 0

    def file_line_count(self, path: str) -> int:
        try:
            text = self._copy_text_from_container(path)
        except (FileNotFoundError, ValueError):
            return 0
        return len(text.splitlines())

    def build_span_catalog(
        self,
        files: tuple[str, ...] | list[str],
        *,
        focus_terms: tuple[str, ...] = (),
        max_spans_per_file: int = 4,
        window_radius: int = 12,
        max_span_lines: int = 40,
    ) -> list[dict]:
        catalog: list[dict] = []
        focus_terms = tuple(term for term in focus_terms if term)
        for file_index, path in enumerate(files, start=1):
            if not path:
                continue
            try:
                text = self._copy_text_from_container(path)
            except (FileNotFoundError, ValueError):
                continue
            lines = text.splitlines()
            if not lines:
                continue
            spans: list[tuple[int, int]] = []
            for term in focus_terms:
                for idx, line in enumerate(lines, start=1):
                    if term in line:
                        start = max(1, idx - window_radius)
                        end = min(len(lines), idx + window_radius)
                        spans.append((start, end))
                        break
                if len(spans) >= max_spans_per_file:
                    break
            if not spans:
                spans.append((1, min(len(lines), max_span_lines)))
            if len(lines) > max_span_lines and len(spans) < max_spans_per_file:
                tail_start = max(1, len(lines) - max_span_lines + 1)
                spans.append((tail_start, len(lines)))
            unique_spans: list[tuple[int, int]] = []
            seen_spans: set[tuple[int, int]] = set()
            for start, end in spans:
                clipped = (start, min(end, start + max_span_lines - 1))
                if clipped in seen_spans:
                    continue
                seen_spans.add(clipped)
                unique_spans.append(clipped)
                if len(unique_spans) >= max_spans_per_file:
                    break
            file_id = f"f{file_index}"
            file_entry = {
                "file_id": file_id,
                "path": path,
                "line_count": len(lines),
                "spans": [],
            }
            for span_index, (start, end) in enumerate(unique_spans, start=1):
                preview = "\n".join(f"{lineno:04d}: {lines[lineno - 1]}" for lineno in range(start, end + 1))
                file_entry["spans"].append(
                    {
                        "span_id": f"{file_id}s{span_index}",
                        "start_line": start,
                        "end_line": end,
                        "preview": preview,
                    }
                )
            catalog.append(file_entry)
        return catalog

    def apply_patch_action(self, action: dict, *, timeout: int = 120) -> SweExecResult:
        target_value = str(action.get("resolved_target_file") or action.get("target_file", "") or "").strip()
        try:
            target = self._workspace_relpath(target_value)
        except ValueError as exc:
            return SweExecResult(stdout="", stderr=str(exc), output=str(exc), returncode=1)
        if not target:
            return SweExecResult(stdout="", stderr="missing target_file", output="missing target_file", returncode=1)

        edit_type = str(action.get("edit_type", "no_action") or "no_action")
        if edit_type == "no_action":
            return SweExecResult(stdout="no_action", stderr="", output="no_action", returncode=0)
        if edit_type not in {"replace", "insert_before", "insert_after", "delete"}:
            message = f"unsupported edit_type: {edit_type}"
            return SweExecResult(stdout="", stderr=message, output=message, returncode=1)

        try:
            resolved_span = action.get("resolved_span", {}) or {}
            start_line = int(resolved_span.get("start_line", action.get("start_line", 0)) or 0)
            end_line = int(resolved_span.get("end_line", action.get("end_line", 0)) or 0)
        except (TypeError, ValueError):
            return SweExecResult(stdout="", stderr="invalid span", output="invalid span", returncode=1)
        if start_line <= 0:
            return SweExecResult(
                stdout="",
                stderr="start_line must be >= 1",
                output="start_line must be >= 1",
                returncode=1,
            )

        try:
            text = self._copy_text_from_container(target)
        except FileNotFoundError:
            return SweExecResult(
                stdout="",
                stderr="target_file does not exist",
                output="target_file does not exist",
                returncode=1,
            )
        lines = text.splitlines(keepends=True)
        replacement = str(action.get("replacement", "") or "")
        if replacement and not replacement.endswith("\n"):
            replacement += "\n"
        replacement_lines = replacement.splitlines(keepends=True)
        line_count = len(lines)
        end_line = max(end_line, start_line)
        start_idx = min(start_line - 1, line_count)
        end_idx = min(end_line, line_count)

        if edit_type == "replace":
            new_lines = lines[:start_idx] + replacement_lines + lines[end_idx:]
        elif edit_type == "insert_before":
            new_lines = lines[:start_idx] + replacement_lines + lines[start_idx:]
        elif edit_type == "insert_after":
            insert_idx = min(end_line, line_count)
            new_lines = lines[:insert_idx] + replacement_lines + lines[insert_idx:]
        else:
            new_lines = lines[:start_idx] + lines[end_idx:]

        try:
            self._copy_text_to_container(target, "".join(new_lines))
        except RuntimeError as exc:
            message = str(exc)
            return SweExecResult(stdout="", stderr=message, output=message, returncode=1)
        stdout = f"applied {edit_type} to {target}:{start_line}-{end_line}"
        return SweExecResult(stdout=stdout, stderr="", output=stdout, returncode=0)

    def syntax_check(self, language: str, changed_files: list[str] | tuple[str, ...], *, timeout: int = 120) -> SweExecResult:
        files = [path for path in changed_files if path]
        if not files:
            return SweExecResult(stdout="no changed files", stderr="", output="no changed files", returncode=0)
        if language == "python":
            py_files = [path for path in files if path.endswith(".py")]
            if not py_files:
                return SweExecResult(stdout="no python files changed", stderr="", output="no python files changed", returncode=0)
            cmd = "cd /app && python -m py_compile " + " ".join(shlex.quote(path) for path in py_files)
            return self.exec(cmd, timeout=timeout)
        if language == "ruby":
            rb_files = [path for path in files if path.endswith(".rb")]
            if not rb_files:
                return SweExecResult(stdout="no ruby files changed", stderr="", output="no ruby files changed", returncode=0)
            cmd = "cd /app && ruby -c " + " ".join(shlex.quote(path) for path in rb_files)
            return self.exec(cmd, timeout=timeout)
        return SweExecResult(stdout=f"syntax check skipped for {language}", stderr="", output=f"syntax check skipped for {language}", returncode=0)

    def cheap_targeted_verify(self, task: dict, related_tests: tuple[str, ...], *, timeout: int = 180) -> SweExecResult:
        related = [path for path in related_tests if path and "/" in path and self.file_exists(path)]
        if not related:
            return SweExecResult(stdout="cheap verify skipped", stderr="", output="cheap verify skipped", returncode=0)
        language = str(task.get("repo_language", "") or "")
        if language == "python":
            cmd = "cd /app && pytest -q " + " ".join(shlex.quote(path) for path in related)
            return self.exec(cmd, timeout=timeout)
        if language == "ruby":
            cmd = "cd /app && bundle exec rspec " + " ".join(shlex.quote(path) for path in related)
            return self.exec(cmd, timeout=timeout)
        return SweExecResult(stdout="cheap verify skipped", stderr="", output="cheap verify skipped", returncode=0)

    @staticmethod
    def render_patch_action(action: dict) -> str:
        return json.dumps(action, ensure_ascii=False, sort_keys=True)

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
