"""Execution runtime backends."""

from __future__ import annotations

import asyncio
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import time
from typing import Iterable

from forge.compute.base import GpuInstance, ProvisionRequest
from forge.compute.manager import ComputeManager
from forge.compute.ssh import SshBackend
from forge.config import ForgeConfig
from forge.execution.bundle import JobBundle
from forge.execution.contracts import (
    ArtifactManifest,
    CollectArtifactsRequest,
    DockerRunMetadata,
    DockerTarget,
    JobKind,
    RunBundleRequest,
    RunHandle,
    RunLogsRequest,
    RunState,
    RunStatus,
    RunStatusRequest,
    SshRunMetadata,
    SshTarget,
    TargonProfile,
    TargonRunMetadata,
    TargonTarget,
    TerminateRunRequest,
)


def _safe_name(raw: str, prefix: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in raw).strip("-")
    return f"{prefix}-{cleaned or 'job'}"[:63]


def _write_archive(source_dir: Path, output_path: Path, arcname: str) -> str:
    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(source_dir, arcname=arcname)
    return str(output_path)


def create_project_snapshot(config: ForgeConfig, output_path: str, include_affinetes: bool = False) -> str:
    root = config.project_root
    include = ["forge", "scripts", "synth_config.json"]
    with tarfile.open(output_path, "w:gz") as tar:
        for name in include:
            path = root / name
            if path.exists():
                tar.add(path, arcname=f"project/{name}")
        if include_affinetes:
            affinetes_root = root.parent / "affinetes"
            if affinetes_root.exists():
                tar.add(affinetes_root, arcname="affinetes", filter=_tar_filter)
    return output_path


def _tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    name = info.name
    skipped = ("/.git/", "/__pycache__/", "/.pytest_cache/", "/.ruff_cache/")
    if any(token in f"/{name}/" for token in skipped):
        return None
    if name.endswith((".pyc", ".pyo")):
        return None
    return info


def create_bundle_archive(bundle: JobBundle, output_path: str) -> str:
    return _write_archive(bundle.path, Path(output_path), "bundle")


def _bundle_remote_workspace(job_id: str) -> str:
    return f"/root/forge-execution/{job_id}"


def _build_remote_wrapper(workspace: str) -> str:
    bundle_root = f"{workspace}/bundle"
    project_root = f"{workspace}/project"
    return (
        f"cd {bundle_root} && "
        f"export BUNDLE_ROOT={bundle_root} PROJECT_ROOT={project_root} && "
        f"bash scripts/entrypoint.sh > artifacts/stdout.log 2> artifacts/stderr.log; "
        f"rc=$?; "
        f"mkdir -p runtime; "
        f"if [ \"$rc\" -eq 0 ]; then state=succeeded; else state=failed; fi; "
        f"printf '{{\"state\":\"%s\",\"exit_code\":%s}}\\n' \"$state\" \"$rc\" > runtime/result.json; "
        f"exit \"$rc\""
    )


def _bootstrap_prefix(project_root: str) -> str:
    return (
        f"bash {project_root}/forge/setup/bootstrap.sh --training && "
        "{ source /data/.affine/activate.sh >/dev/null 2>&1 || true; }; "
    )


def _local_result_path(bundle: JobBundle) -> Path:
    return bundle.runtime_dir / "result.json"


def _read_json_if_exists(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


_RUNTIME_ENV_ALLOWLIST = (
    "HF_TOKEN",
    "WANDB_API_KEY",
    "AMAP_API_KEY",
    "AMAP_MAPS_API_KEY",
    "QWEN_API_KEY",
    "CHUTES_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "TAOSTATS_API_KEY",
)


def _docker_bundle_wrapper() -> str:
    return (
        "cd /workspace/bundle && "
        "mkdir -p artifacts runtime && "
        "export BUNDLE_ROOT=/workspace/bundle PROJECT_ROOT=/workspace/project PYTHONPATH=/workspace/project:${PYTHONPATH:-} && "
        "bash scripts/entrypoint.sh > artifacts/stdout.log 2> artifacts/stderr.log; "
        "rc=$?; "
        "if [ \"$rc\" -eq 0 ]; then state=succeeded; else state=failed; fi; "
        "printf '{\"state\":\"%s\",\"exit_code\":%s}\\n' \"$state\" \"$rc\" > runtime/result.json; "
        "exit \"$rc\""
    )


class DockerRuntime:
    def __init__(self, config: ForgeConfig):
        self.config = config

    async def run(self, request: RunBundleRequest) -> RunHandle:
        bundle = JobBundle(request.bundle_path)
        target = request.target
        if not isinstance(target, DockerTarget):
            raise ValueError("DockerRuntime requires DockerTarget")
        job = bundle.load_job()
        image_name = target.image or job.runtime_preferences.image or "wangtong123/affine-forge:latest"
        container_name = _safe_name(job.job_id, "forge-worker")
        project_root = str(self.config.project_root.resolve())
        bundle_root = str(bundle.path.resolve())
        runtime_profile = job.runtime_preferences.profile or "image"
        data_root = bundle.path / "runtime" / "data"
        data_root.mkdir(parents=True, exist_ok=True)
        cmd = [
            "docker",
            "run",
            "--name",
            container_name,
            "-v",
            f"{project_root}:/workspace/project",
            "-v",
            f"{bundle_root}:/workspace/bundle",
            "-v",
            f"{data_root.resolve()}:/data",
            "-w",
            "/workspace/project",
        ]
        if not target.detach:
            cmd.append("--rm")
        if target.detach:
            cmd.append("-d")
        cmd.extend(
            [
                image_name,
                "bash",
                "-lc",
                (_bootstrap_prefix("/workspace/project") if runtime_profile == "bootstrap" else "")
                + _docker_bundle_wrapper(),
            ]
        )
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            bundle.record_local_artifacts()
            logs = []
            for name in ("stdout.log", "stderr.log"):
                path = bundle.artifacts_dir / name
                if path.exists():
                    logs.append(path.read_text(encoding="utf-8", errors="replace"))
            detail = "\n".join(part for part in [proc.stderr, proc.stdout, *logs] if part).strip()
            raise RuntimeError(detail or "Docker runtime failed")

        handle = RunHandle(
            runtime_kind="docker",
            run_id=proc.stdout.strip() if target.detach else container_name,
            target_id=container_name,
            bundle_path=str(bundle.path),
            metadata=DockerRunMetadata(
                container_name=container_name,
                image=image_name,
                detach=target.detach,
                profile=runtime_profile,
            ),
        )
        bundle.write_run_handle(handle)
        if not target.detach:
            result = _read_json_if_exists(_local_result_path(bundle))
            state = RunState(result.get("state", "succeeded" if proc.returncode == 0 else "failed"))
            bundle.write_run_status(
                RunStatus(
                    runtime_kind="docker",
                    run_id=handle.run_id,
                    state=state,
                    metadata={"container_name": container_name, "exit_code": result.get("exit_code", proc.returncode)},
                )
            )
            bundle.record_local_artifacts()
        return handle

    async def status(self, request: RunStatusRequest) -> RunStatus:
        handle = request.handle
        metadata = handle.metadata
        if not isinstance(metadata, DockerRunMetadata):
            raise ValueError("Docker run handle missing DockerRunMetadata")
        container = metadata.container_name
        bundle = JobBundle(handle.bundle_path)
        result = _read_json_if_exists(_local_result_path(bundle))
        if result:
            state = RunState(result.get("state", "failed"))
            return RunStatus(runtime_kind="docker", run_id=handle.run_id, state=state, metadata={"container_name": container, **result})
        proc = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Status}}", container],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return RunStatus(runtime_kind="docker", run_id=handle.run_id, state=RunState.FAILED, detail=proc.stderr.strip())
        raw = proc.stdout.strip()
        state = {
            "created": RunState.STARTING,
            "running": RunState.RUNNING,
            "exited": RunState.FAILED,
            "dead": RunState.FAILED,
        }.get(raw, RunState.SUBMITTED)
        return RunStatus(runtime_kind="docker", run_id=handle.run_id, state=state, detail=raw, metadata={"container_name": container})

    async def logs(self, request: RunLogsRequest) -> str:
        handle = request.handle
        metadata = handle.metadata
        if not isinstance(metadata, DockerRunMetadata):
            raise ValueError("Docker run handle missing DockerRunMetadata")
        container = metadata.container_name
        proc = subprocess.run(["docker", "logs", "--tail", str(request.tail), container], capture_output=True, text=True)
        output = (proc.stdout + proc.stderr).strip()
        if proc.returncode == 0 and output:
            return output
        bundle = JobBundle(handle.bundle_path)
        fallback_parts = []
        for name in ("stdout.log", "stderr.log"):
            path = bundle.artifacts_dir / name
            if path.exists():
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                tail_lines = "\n".join(lines[-request.tail:])
                if tail_lines:
                    fallback_parts.append(tail_lines)
        return "\n".join(part for part in fallback_parts if part).strip() or output

    async def collect(self, request: CollectArtifactsRequest) -> ArtifactManifest:
        bundle = JobBundle(request.handle.bundle_path)
        return bundle.record_local_artifacts()

    async def terminate(self, request: TerminateRunRequest) -> None:
        metadata = request.handle.metadata
        if not isinstance(metadata, DockerRunMetadata):
            raise ValueError("Docker run handle missing DockerRunMetadata")
        subprocess.run(["docker", "rm", "-f", metadata.container_name], capture_output=True, text=True)


class SshRuntime:
    def __init__(self, config: ForgeConfig):
        self.config = config
        self.backend = SshBackend(str(config.machines_file))

    async def _resolve_target(self, target: str) -> GpuInstance:
        instances = await self.backend.list_instances()
        for instance in instances:
            if instance.id == target or instance.host == target:
                return instance
        raise ValueError(f"Unknown SSH target: {target}")

    async def run(self, request: RunBundleRequest) -> RunHandle:
        bundle = JobBundle(request.bundle_path)
        target = request.target
        if not isinstance(target, SshTarget):
            raise ValueError("SshRuntime requires SshTarget")
        if not target.target:
            raise ValueError("SSH runtime requires --target")
        instance = await self._resolve_target(target.target)
        job = bundle.load_job()
        runtime_profile = target.profile or job.runtime_preferences.profile or ""
        workspace = _bundle_remote_workspace(job.job_id)
        session = _safe_name(job.job_id, "worker")

        with tempfile.TemporaryDirectory() as tmp:
            project_tgz = create_project_snapshot(
                self.config,
                os.path.join(tmp, "project.tar.gz"),
                include_affinetes=(job.kind == JobKind.EVAL),
            )
            bundle_tgz = create_bundle_archive(bundle, os.path.join(tmp, "bundle.tar.gz"))
            await self.backend.exec(instance, f"rm -rf {workspace} && mkdir -p {workspace}", timeout=30)
            await self.backend.upload(instance, project_tgz, f"{workspace}/project.tar.gz")
            await self.backend.upload(instance, bundle_tgz, f"{workspace}/bundle.tar.gz")
            setup_cmd = (
                f"cd {workspace} && "
                f"mkdir -p project bundle && "
                f"tar -xzf project.tar.gz -C . && "
                f"tar -xzf bundle.tar.gz -C ."
            )
            rc, _, stderr = await self.backend.exec(instance, setup_cmd, timeout=120)
            if rc != 0:
                raise RuntimeError(f"SSH workspace setup failed: {stderr}")
            wrapper = (
                (_bootstrap_prefix(f"{workspace}/project") if runtime_profile == "bootstrap" else "")
                + _build_remote_wrapper(workspace)
            )
            if target.detach:
                launch_cmd = f"screen -dmS {session} bash -lc {json.dumps(wrapper)}"
            else:
                launch_cmd = f"bash -lc {json.dumps(wrapper)}"
            rc, stdout, stderr = await self.backend.exec(instance, launch_cmd, timeout=60)
            if rc != 0:
                raise RuntimeError(f"SSH launch failed: {stderr or stdout}")

        handle = RunHandle(
            runtime_kind="ssh",
            run_id=session,
            target_id=instance.id,
            bundle_path=str(bundle.path),
            metadata=SshRunMetadata(
                session=session,
                workspace=workspace,
                host=instance.host or "",
                target=instance.id,
                profile=runtime_profile,
            ),
        )
        bundle.write_run_handle(handle)
        bundle.write_run_status(RunStatus(runtime_kind="ssh", run_id=session, state=RunState.SUBMITTED, metadata={"target": instance.id}))
        return handle

    async def status(self, request: RunStatusRequest) -> RunStatus:
        handle = request.handle
        metadata = handle.metadata
        if not isinstance(metadata, SshRunMetadata):
            raise ValueError("SSH run handle missing SshRunMetadata")
        instance = await self._resolve_target(handle.target_id)
        workspace = metadata.workspace
        session = metadata.session
        rc, stdout, _ = await self.backend.exec(
            instance,
            f"test -f {workspace}/bundle/runtime/result.json && cat {workspace}/bundle/runtime/result.json",
            timeout=15,
        )
        if rc == 0 and stdout.strip():
            raw = json.loads(stdout)
            return RunStatus(runtime_kind="ssh", run_id=handle.run_id, state=RunState(raw["state"]), metadata=raw)
        rc, stdout, _ = await self.backend.exec(instance, "screen -ls 2>/dev/null || true", timeout=10)
        if rc == 0 and session in stdout:
            return RunStatus(runtime_kind="ssh", run_id=handle.run_id, state=RunState.RUNNING, metadata={"session": session})
        return RunStatus(runtime_kind="ssh", run_id=handle.run_id, state=RunState.FAILED, detail="session not found")

    async def logs(self, request: RunLogsRequest) -> str:
        handle = request.handle
        metadata = handle.metadata
        if not isinstance(metadata, SshRunMetadata):
            raise ValueError("SSH run handle missing SshRunMetadata")
        instance = await self._resolve_target(handle.target_id)
        workspace = metadata.workspace
        _, stdout, stderr = await self.backend.exec(
            instance,
            f"tail -n {request.tail} {workspace}/bundle/artifacts/stdout.log 2>/dev/null; "
            f"tail -n {request.tail} {workspace}/bundle/artifacts/stderr.log 2>/dev/null",
            timeout=20,
        )
        return (stdout + stderr).strip()

    async def collect(self, request: CollectArtifactsRequest) -> ArtifactManifest:
        handle = request.handle
        metadata = handle.metadata
        if not isinstance(metadata, SshRunMetadata):
            raise ValueError("SSH run handle missing SshRunMetadata")
        instance = await self._resolve_target(handle.target_id)
        workspace = metadata.workspace
        bundle = JobBundle(handle.bundle_path)
        await self.backend.download(instance, f"{workspace}/bundle/artifacts", str(bundle.path))
        return bundle.record_local_artifacts()

    async def terminate(self, request: TerminateRunRequest) -> None:
        handle = request.handle
        metadata = handle.metadata
        if not isinstance(metadata, SshRunMetadata):
            raise ValueError("SSH run handle missing SshRunMetadata")
        instance = await self._resolve_target(handle.target_id)
        session = metadata.session
        workspace = metadata.workspace
        await self.backend.exec(instance, f"screen -S {session} -X quit 2>/dev/null || true; rm -rf {workspace}", timeout=30)


class TargonRuntime:
    def __init__(self, config: ForgeConfig):
        self.config = config
        self.compute = ComputeManager(config)

    def _artifact_name(self, job_id: str, suffix: str) -> str:
        return f"execution/{job_id}-{suffix}"

    def _runtime_env(self, bundle: JobBundle) -> dict[str, str]:
        job = bundle.load_job()
        env = {"HF_TOKEN": self.config.hf_token}
        for key in _RUNTIME_ENV_ALLOWLIST:
            value = os.environ.get(key, "")
            if value:
                env[key] = value
        env.update(job.runtime_preferences.runtime_env)
        return env

    def _upload_file(self, local_path: str, repo_id: str, remote_name: str) -> str:
        from huggingface_hub import HfApi

        api = HfApi(token=self.config.hf_token)
        api.upload_file(
            path_or_fileobj=local_path,
            path_in_repo=remote_name,
            repo_id=repo_id,
            repo_type="dataset",
        )
        return remote_name

    def _download_file(self, repo_id: str, remote_name: str, local_dir: str) -> str:
        from huggingface_hub import hf_hub_download

        return hf_hub_download(repo_id=repo_id, repo_type="dataset", filename=remote_name, local_dir=local_dir, token=self.config.hf_token)

    def _runtime_script(self, repo_id: str, project_name: str, bundle_name: str, artifact_name: str, profile: str) -> str:
        bootstrap_line = ""
        activate_line = ""
        if profile == "bootstrap":
            bootstrap_line = "bash /workspace/project/forge/setup/bootstrap.sh --training\n"
            activate_line = "source /data/.affine/activate.sh >/dev/null 2>&1 || true\n"
        return f"""set -euo pipefail
mkdir -p /workspace
mkdir -p /tmp/health
echo ok > /tmp/health/index.html
python3 -m http.server 8080 --directory /tmp/health > /tmp/health/server.log 2>&1 &
python3 - <<'PY'
import os, tarfile, urllib.request, ssl
repo = {repo_id!r}
token = os.environ.get("HF_TOKEN", "")
base = f"https://huggingface.co/datasets/{{repo}}/resolve/main/"
headers = {{"Authorization": f"Bearer {{token}}", "User-Agent": "python"}}
ctx = ssl.create_default_context()
for remote_name in [{project_name!r}, {bundle_name!r}]:
    req = urllib.request.Request(base + remote_name, headers=headers)
    local = f"/workspace/{{os.path.basename(remote_name)}}"
    with urllib.request.urlopen(req, context=ctx, timeout=600) as resp, open(local, "wb") as handle:
        handle.write(resp.read())
    with tarfile.open(local, "r:gz") as tar:
        tar.extractall("/workspace")
PY
{bootstrap_line}{activate_line}cd /workspace/bundle
export BUNDLE_ROOT=/workspace/bundle PROJECT_ROOT=/workspace/project PYTHONPATH=/workspace/project:${{PYTHONPATH:-}}
bash scripts/entrypoint.sh > artifacts/stdout.log 2> artifacts/stderr.log || STATUS=$?
STATUS="${{STATUS:-0}}"
mkdir -p /workspace/bundle/runtime
if [ "$STATUS" -eq 0 ]; then STATE=succeeded; else STATE=failed; fi
printf '{{"state":"%s","exit_code":%s}}\n' "$STATE" "$STATUS" > /workspace/bundle/runtime/result.json
tar -czf /workspace/artifacts.tgz -C /workspace bundle/artifacts bundle/runtime
python3 - <<'PY'
from huggingface_hub import HfApi
import os
api = HfApi(token=os.environ.get("HF_TOKEN", ""))
api.upload_file(path_or_fileobj="/workspace/artifacts.tgz", path_in_repo={artifact_name!r}, repo_id={repo_id!r}, repo_type="dataset")
PY
exit "$STATUS"
"""

    async def run(self, request: RunBundleRequest) -> RunHandle:
        bundle = JobBundle(request.bundle_path)
        target = request.target
        if not isinstance(target, TargonTarget):
            raise ValueError("TargonRuntime requires TargonTarget")
        if not target.dataset_repo:
            raise ValueError("Targon runtime requires --dataset-repo")
        if not self.config.hf_token:
            raise ValueError("HF_TOKEN is required for Targon runtime")
        job = bundle.load_job()
        runtime_profile = (target.profile.value if isinstance(target.profile, TargonProfile) else str(target.profile)) or job.runtime_preferences.profile or "image"
        runtime_image = target.image or job.runtime_preferences.image or (
            "pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel" if runtime_profile == "bootstrap" else "wangtong123/affine-forge:latest"
        )

        with tempfile.TemporaryDirectory() as tmp:
            project_tgz = create_project_snapshot(
                self.config,
                os.path.join(tmp, "project.tar.gz"),
                include_affinetes=(job.kind == JobKind.EVAL),
            )
            bundle_tgz = create_bundle_archive(bundle, os.path.join(tmp, "bundle.tar.gz"))
            project_name = self._artifact_name(job.job_id, "project.tar.gz")
            bundle_name = self._artifact_name(job.job_id, "bundle.tar.gz")
            artifact_name = self._artifact_name(job.job_id, "artifacts.tar.gz")
            self._upload_file(project_tgz, target.dataset_repo, project_name)
            self._upload_file(bundle_tgz, target.dataset_repo, bundle_name)
            command = self._runtime_script(target.dataset_repo, project_name, bundle_name, artifact_name, runtime_profile)
            targon = self.compute.get_backend("targon")
            instance = await targon.provision(
                ProvisionRequest(
                    backend="targon",
                    gpu_type=target.gpu_type or job.resources.gpu_type or "H200",
                    name=_safe_name(job.job_id, "forge-worker"),
                    image=runtime_image,
                    command=["/bin/bash", "-lc"],
                    args=[command],
                    env=self._runtime_env(bundle),
                    service_port=8080,
                )
            )

        handle = RunHandle(
            runtime_kind="targon",
            run_id=instance.id,
            target_id=instance.id,
            bundle_path=str(bundle.path),
            metadata=TargonRunMetadata(
                profile=runtime_profile,
                image=runtime_image,
                dataset_repo=target.dataset_repo,
                artifact_name=artifact_name,
                bundle_name=bundle_name,
                project_name=project_name,
                url=instance.url or "",
            ),
        )
        bundle.write_run_handle(handle)
        bundle.write_run_status(RunStatus(runtime_kind="targon", run_id=instance.id, state=RunState.SUBMITTED, metadata={"url": instance.url or ""}))
        return handle

    async def status(self, request: RunStatusRequest) -> RunStatus:
        handle = request.handle
        metadata = handle.metadata
        url = metadata.url if isinstance(metadata, TargonRunMetadata) else ""
        targon = self.compute.get_backend("targon")
        instance = GpuInstance(id=handle.run_id, backend="targon", gpu_type="unknown", status="unknown", url=url)
        health = await targon.health_check(instance)
        raw = str(health.get("status", "submitted")).lower()
        if "ready" in raw or "running" in raw:
            state = RunState.RUNNING
        elif "error" in raw or "fail" in raw:
            state = RunState.FAILED
        else:
            state = RunState.SUBMITTED
        return RunStatus(runtime_kind="targon", run_id=handle.run_id, state=state, detail=raw, metadata=health)

    async def logs(self, request: RunLogsRequest) -> str:
        handle = request.handle
        targon = self.compute.get_backend("targon")
        lines = await targon.logs_snapshot(handle.run_id, tail=request.tail)
        return "".join(lines).strip()

    async def collect(self, request: CollectArtifactsRequest) -> ArtifactManifest:
        handle = request.handle
        metadata = handle.metadata
        if not isinstance(metadata, TargonRunMetadata):
            raise ValueError("Targon run handle missing TargonRunMetadata")
        bundle = JobBundle(handle.bundle_path)
        with tempfile.TemporaryDirectory() as tmp:
            archive = self._download_file(metadata.dataset_repo, metadata.artifact_name, tmp)
            with tarfile.open(archive, "r:gz") as tar:
                tar.extractall(bundle.path)
        return bundle.record_local_artifacts()

    async def terminate(self, request: TerminateRunRequest) -> None:
        handle = request.handle
        instance = GpuInstance(id=handle.run_id, backend="targon", gpu_type="unknown", status="running")
        await self.compute.terminate(instance)
