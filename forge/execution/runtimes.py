"""Execution runtime backends."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import tarfile
import tempfile
from typing import Iterable

from forge.compute.base import GpuInstance
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


def _runtime_staging_repo(config: ForgeConfig) -> str:
    repo = config.hf_runtime_repo or config.hf_backup_repo
    if repo and config.hf_token:
        return repo
    return ""


def _runtime_staging_paths(job_id: str) -> tuple[str, str]:
    prefix = f"runtime-bundles/{job_id}"
    return f"{prefix}/project.tar.gz", f"{prefix}/bundle.tar.gz"


def _upload_runtime_archive(local_path: str, repo_id: str, path_in_repo: str, token: str) -> None:
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    api.upload_file(
        path_or_fileobj=local_path,
        path_in_repo=path_in_repo,
        repo_id=repo_id,
        repo_type="model",
        commit_message=f"runtime: upload {path_in_repo}",
    )


_RUNTIME_ENV_ALLOWLIST = (
    "HF_TOKEN",
    "HF_DATASET_REPO",
    "WANDB_API_KEY",
    "AMAP_API_KEY",
    "AMAP_MAPS_API_KEY",
    "QWEN_API_KEY",
    "CHUTES_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "COINGECKO_API_KEY",
    "TAOSTATS_API_KEY",
    "SWE_DISTILL_SSH",
    "SWE_DISTILL_SSH_KEY",
    "SWE_DISTILL_SSH_PORT",
    "PLAYWRIGHT_BROWSERS_PATH",
    "LIVEWEB_CACHE_DIR",
)

_RENTAL_SSH_PREP_TIMEOUT = 180
_RENTAL_SSH_QUERY_TIMEOUT = 120


def _docker_bundle_wrapper() -> str:
    return (
        "cd /workspace/bundle && "
        "mkdir -p artifacts runtime && "
        "export BUNDLE_ROOT=/workspace/bundle PROJECT_ROOT=/workspace/project PYTHONPATH=/workspace/project:${PYTHONPATH:-} FORGE_PYTHON=/opt/affine-venv/bin/python FORGE_SKIP_DOTENV=1 && "
        "bash scripts/entrypoint.sh > artifacts/stdout.log 2> artifacts/stderr.log; "
        "rc=$?; "
        "if [ \"$rc\" -eq 0 ]; then state=succeeded; else state=failed; fi; "
        "printf '{\"state\":\"%s\",\"exit_code\":%s}\\n' \"$state\" \"$rc\" > runtime/result.json; "
        "exit \"$rc\""
    )


def _remote_docker_wrapper(*, use_hf_staging: bool) -> str:
    bundle_root = "/workspace/bundle"
    project_root = "/workspace/project"
    prepare_archives = (
        "python3 - <<'PY'\n"
        "import os, ssl, urllib.request\n"
        "repo = os.environ['AFFINE_HF_STAGING_REPO']\n"
        "token = os.environ.get('HF_TOKEN', '')\n"
        "base = f'https://huggingface.co/{repo}/resolve/main/'\n"
        "ctx = ssl.create_default_context()\n"
        "headers = {'User-Agent': 'affine-runtime'}\n"
        "if token:\n"
        "    headers['Authorization'] = f'Bearer {token}'\n"
        "files = [\n"
        "    (os.environ['AFFINE_HF_PROJECT_PATH'], '/workspace/downloads/project.tar.gz'),\n"
        "    (os.environ['AFFINE_HF_BUNDLE_PATH'], '/workspace/downloads/bundle.tar.gz'),\n"
        "]\n"
        "for path_in_repo, dest in files:\n"
        "    req = urllib.request.Request(base + path_in_repo, headers=headers)\n"
        "    with urllib.request.urlopen(req, context=ctx, timeout=3600) as src, open(dest, 'wb') as out:\n"
        "        while True:\n"
        "            chunk = src.read(1024 * 1024)\n"
        "            if not chunk:\n"
        "                break\n"
        "            out.write(chunk)\n"
        "PY\n"
        if use_hf_staging
        else "cp /staging/project.tar.gz /workspace/downloads/project.tar.gz\n"
        "cp /staging/bundle.tar.gz /workspace/downloads/bundle.tar.gz\n"
    )
    return (
        "set -euo pipefail\n"
        "mkdir -p /workspace/project /workspace/bundle /workspace/downloads /data\n"
        f"{prepare_archives}"
        "tar -xzf /workspace/downloads/project.tar.gz -C /workspace\n"
        "tar -xzf /workspace/downloads/bundle.tar.gz -C /workspace\n"
        f"cd {bundle_root}\n"
        "mkdir -p artifacts runtime\n"
        f"export BUNDLE_ROOT={bundle_root} PROJECT_ROOT={project_root} PYTHONPATH={project_root}:${{PYTHONPATH:-}} FORGE_PYTHON=/opt/affine-venv/bin/python FORGE_SKIP_DOTENV=1\n"
        "bash scripts/entrypoint.sh > artifacts/stdout.log 2> artifacts/stderr.log\n"
        "rc=$?\n"
        "if [ \"$rc\" -eq 0 ]; then state=succeeded; else state=failed; fi\n"
        "printf '{\"state\":\"%s\",\"exit_code\":%s}\\n' \"$state\" \"$rc\" > runtime/result.json\n"
        "exit \"$rc\"\n"
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
            await self.backend.exec(
                instance,
                f"rm -rf {workspace} && mkdir -p {workspace}",
                timeout=_RENTAL_SSH_PREP_TIMEOUT,
            )
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
        self.backend = SshBackend(str(config.machines_file))

    async def _resolve_target(self, target: str) -> GpuInstance:
        instances = await self.backend.list_instances()
        for instance in instances:
            if instance.id == target or instance.host == target:
                return instance
        raise ValueError(f"Unknown Targon rental target: {target}")

    def _runtime_env(self, bundle: JobBundle) -> dict[str, str]:
        job = bundle.load_job()
        env = {}
        if self.config.hf_token:
            env["HF_TOKEN"] = self.config.hf_token
        for key in _RUNTIME_ENV_ALLOWLIST:
            value = os.environ.get(key, "")
            if value:
                env[key] = value
        env.update(job.runtime_preferences.runtime_env)
        return env

    async def run(self, request: RunBundleRequest) -> RunHandle:
        bundle = JobBundle(request.bundle_path)
        target = request.target
        if not isinstance(target, TargonTarget):
            raise ValueError("TargonRuntime requires TargonTarget")
        if not target.target:
            raise ValueError("Targon rental runtime requires --target")
        job = bundle.load_job()
        runtime_profile = (target.profile.value if isinstance(target.profile, TargonProfile) else str(target.profile)) or TargonProfile.RENTAL.value
        runtime_image = target.image or job.runtime_preferences.image or "wangtong123/affine-forge:latest"
        instance = await self._resolve_target(target.target)
        workspace = _bundle_remote_workspace(job.job_id)
        container_name = _safe_name(job.job_id, "forge-worker")
        staging_repo = _runtime_staging_repo(self.config)
        use_hf_staging = bool(staging_repo)
        project_archive_path, bundle_archive_path = _runtime_staging_paths(job.job_id)
        env_flags = " ".join(
            f"-e {shlex.quote(f'{key}={value}')}"
            for key, value in self._runtime_env(bundle).items()
        )
        staging_env_flags = " ".join(
            [
                f"-e {shlex.quote(f'AFFINE_USE_HF_STAGING={1 if use_hf_staging else 0}')}",
                *(
                    [
                        f"-e {shlex.quote(f'AFFINE_HF_STAGING_REPO={staging_repo}')}",
                        f"-e {shlex.quote(f'AFFINE_HF_PROJECT_PATH={project_archive_path}')}",
                        f"-e {shlex.quote(f'AFFINE_HF_BUNDLE_PATH={bundle_archive_path}')}",
                    ]
                    if use_hf_staging
                    else []
                ),
            ]
        )
        wrapper = _remote_docker_wrapper(use_hf_staging=use_hf_staging)

        with tempfile.TemporaryDirectory() as tmp:
            project_tgz = create_project_snapshot(
                self.config,
                os.path.join(tmp, "project.tar.gz"),
                include_affinetes=(job.kind == JobKind.EVAL),
            )
            bundle_tgz = create_bundle_archive(bundle, os.path.join(tmp, "bundle.tar.gz"))
            await self.backend.exec(
                instance,
                f"rm -rf {workspace} && mkdir -p {workspace}/project {workspace}/bundle {workspace}/data",
                timeout=_RENTAL_SSH_PREP_TIMEOUT,
            )
            if use_hf_staging:
                _upload_runtime_archive(project_tgz, staging_repo, project_archive_path, self.config.hf_token)
                _upload_runtime_archive(bundle_tgz, staging_repo, bundle_archive_path, self.config.hf_token)
            else:
                await self.backend.upload(instance, project_tgz, f"{workspace}/project.tar.gz")
                await self.backend.upload(instance, bundle_tgz, f"{workspace}/bundle.tar.gz")
            docker_mode_flag = "-d" if target.detach else "--rm"
            remote_script = (
                "set -euo pipefail; "
                f"docker rm -f {container_name} >/dev/null 2>&1 || true; "
                f"docker pull {runtime_image}; "
                f"docker run --gpus all --name {container_name} {docker_mode_flag} "
                f"-v {workspace}:/staging "
                f"-v {workspace}/project:/workspace/project "
                f"-v {workspace}/bundle:/workspace/bundle "
                f"-v {workspace}/data:/data "
                f"-w /workspace/project "
                f"{env_flags} "
                f"{staging_env_flags} "
                f"{runtime_image} "
                f"bash -lc {shlex.quote(wrapper)}"
            )
            remote_cmd = f"bash -lc {shlex.quote(remote_script)}"
            rc, out, err = await self.backend.exec(instance, remote_cmd, timeout=3600)
            if rc != 0:
                raise RuntimeError((err or out or "Targon rental runtime failed").strip())

        handle = RunHandle(
            runtime_kind="targon",
            run_id=container_name,
            target_id=instance.id,
            bundle_path=str(bundle.path),
            metadata=TargonRunMetadata(
                profile=runtime_profile,
                target=instance.id,
                host=instance.host or "",
                workspace=workspace,
                container_name=container_name,
                image=runtime_image,
                staging_repo=staging_repo,
                project_archive_path=project_archive_path,
                bundle_archive_path=bundle_archive_path,
            ),
        )
        bundle.write_run_handle(handle)
        bundle.write_run_status(
            RunStatus(
                runtime_kind="targon",
                run_id=handle.run_id,
                state=RunState.SUBMITTED,
                metadata={"target": instance.id, "host": instance.host or "", "container_name": container_name},
            )
        )
        return handle

    async def status(self, request: RunStatusRequest) -> RunStatus:
        handle = request.handle
        metadata = handle.metadata
        if not isinstance(metadata, TargonRunMetadata):
            raise ValueError("Targon run handle missing TargonRunMetadata")
        instance = await self._resolve_target(metadata.target or handle.target_id)
        workspace = metadata.workspace
        rc, out, _ = await self.backend.exec(
            instance,
            f"test -f {workspace}/bundle/runtime/result.json && cat {workspace}/bundle/runtime/result.json || true",
            timeout=_RENTAL_SSH_QUERY_TIMEOUT,
        )
        result = {}
        if rc == 0 and out.strip():
            result = json.loads(out.strip())
        if result:
            state = RunState(result.get("state", "failed"))
            return RunStatus(runtime_kind="targon", run_id=handle.run_id, state=state, metadata={"container_name": metadata.container_name, "host": instance.host or "", **result})
        rc, out, err = await self.backend.exec(
            instance,
            f"docker inspect -f '{{{{.State.Status}}}}' {metadata.container_name}",
            timeout=_RENTAL_SSH_QUERY_TIMEOUT,
        )
        if rc != 0:
            return RunStatus(runtime_kind="targon", run_id=handle.run_id, state=RunState.FAILED, detail=(err or out).strip())
        raw = out.strip().lower()
        state = {
            "created": RunState.STARTING,
            "restarting": RunState.STARTING,
            "running": RunState.RUNNING,
            "exited": RunState.FAILED,
            "dead": RunState.FAILED,
        }.get(raw, RunState.SUBMITTED)
        return RunStatus(
            runtime_kind="targon",
            run_id=handle.run_id,
            state=state,
            detail=raw,
            metadata={"container_name": metadata.container_name, "host": instance.host or "", "target": instance.id},
        )

    async def logs(self, request: RunLogsRequest) -> str:
        handle = request.handle
        metadata = handle.metadata
        if not isinstance(metadata, TargonRunMetadata):
            raise ValueError("Targon run handle missing TargonRunMetadata")
        instance = await self._resolve_target(metadata.target or handle.target_id)
        rc, out, err = await self.backend.exec(
            instance,
            f"docker logs --tail {request.tail} {metadata.container_name}",
            timeout=_RENTAL_SSH_QUERY_TIMEOUT,
        )
        output = (out + err).strip()
        if output:
            return output
        rc, out, err = await self.backend.exec(
            instance,
            (
                f"for path in {metadata.workspace}/bundle/artifacts/stdout.log {metadata.workspace}/bundle/artifacts/stderr.log; do "
                "if [ -f \"$path\" ]; then tail -n "
                f"{request.tail} \"$path\"; fi; done"
            ),
            timeout=_RENTAL_SSH_QUERY_TIMEOUT,
        )
        return (out + err).strip()

    async def collect(self, request: CollectArtifactsRequest) -> ArtifactManifest:
        handle = request.handle
        metadata = handle.metadata
        if not isinstance(metadata, TargonRunMetadata):
            raise ValueError("Targon run handle missing TargonRunMetadata")
        bundle = JobBundle(handle.bundle_path)
        instance = await self._resolve_target(metadata.target or handle.target_id)
        await self.backend.download(instance, f"{metadata.workspace}/bundle/artifacts", str(bundle.path))
        await self.backend.download(instance, f"{metadata.workspace}/bundle/runtime", str(bundle.path))
        return bundle.record_local_artifacts()

    async def terminate(self, request: TerminateRunRequest) -> None:
        handle = request.handle
        metadata = handle.metadata
        if not isinstance(metadata, TargonRunMetadata):
            raise ValueError("Targon run handle missing TargonRunMetadata")
        instance = await self._resolve_target(metadata.target or handle.target_id)
        await self.backend.exec(
            instance,
            f"docker rm -f {metadata.container_name} >/dev/null 2>&1 || true; rm -rf {metadata.workspace}",
            timeout=_RENTAL_SSH_QUERY_TIMEOUT,
        )
