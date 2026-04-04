"""Execution runtime backends."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import tarfile
import tempfile

from forge.compute.base import GpuInstance
from forge.compute.ssh import SshBackend
from forge.config import ForgeConfig
from forge.execution.bundle import JobBundle
from forge.execution.contracts import (
    ArtifactManifest,
    CollectArtifactsRequest,
    ExecutionRequest,
    LaunchModeKind,
    LocalDockerRunMetadata,
    LocalHostRunMetadata,
    PlacementKind,
    RunHandle,
    RunLogsRequest,
    RunState,
    RunStatus,
    RunStatusRequest,
    TargonRentalDockerRunMetadata,
    TerminateRunRequest,
)


def _safe_name(raw: str, prefix: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in raw).strip("-")
    return f"{prefix}-{cleaned or 'job'}"[:63]


def _write_archive(source_dir: Path, output_path: Path, arcname: str) -> str:
    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(source_dir, arcname=arcname)
    return str(output_path)


def _tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    name = info.name
    skipped = ("/.git/", "/__pycache__/", "/.pytest_cache/", "/.ruff_cache/")
    if any(token in f"/{name}/" for token in skipped):
        return None
    if name.endswith((".pyc", ".pyo")):
        return None
    return info


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


def create_bundle_archive(bundle: JobBundle, output_path: str) -> str:
    return _write_archive(bundle.path, Path(output_path), "bundle")


def _bundle_remote_workspace(job_id: str) -> str:
    return f"/root/forge-execution/{job_id}"


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


def _local_result_path(bundle: JobBundle) -> Path:
    return bundle.runtime_dir / "result.json"


def _read_json_if_exists(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_result(bundle: JobBundle, returncode: int) -> None:
    state = "succeeded" if returncode == 0 else "failed"
    _local_result_path(bundle).write_text(
        json.dumps({"state": state, "exit_code": returncode}) + "\n",
        encoding="utf-8",
    )


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


def _tail_local_logs(bundle: JobBundle, tail: int) -> str:
    fallback_parts = []
    for name in ("stdout.log", "stderr.log"):
        path = bundle.artifacts_dir / name
        if path.exists():
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            tail_lines = "\n".join(lines[-tail:])
            if tail_lines:
                fallback_parts.append(tail_lines)
    return "\n".join(part for part in fallback_parts if part).strip()


def _runtime_env(config: ForgeConfig, bundle: JobBundle, request: ExecutionRequest) -> dict[str, str]:
    job = bundle.load_job()
    env = {}
    if config.hf_token:
        env["HF_TOKEN"] = config.hf_token
    for key in _RUNTIME_ENV_ALLOWLIST:
        value = os.environ.get(key, "")
        if value:
            env[key] = value
    env.update(job.runtime_env)
    env.update(request.runtime_env)
    return env


class LocalHostProcessRuntime:
    def __init__(self, config: ForgeConfig):
        self.config = config

    async def run(self, request: ExecutionRequest) -> RunHandle:
        if request.placement.kind != PlacementKind.LOCAL or request.launch_mode.kind != LaunchModeKind.HOST_PROCESS:
            raise ValueError("LocalHostProcessRuntime requires local + host_process")
        bundle = JobBundle(request.bundle_path)
        job = bundle.load_job()
        bundle.ensure_structure()
        stdout_path = bundle.artifacts_dir / "stdout.log"
        stderr_path = bundle.artifacts_dir / "stderr.log"
        env = os.environ.copy()
        env.update(_runtime_env(self.config, bundle, request))
        env["BUNDLE_ROOT"] = str(bundle.path.resolve())
        env["PROJECT_ROOT"] = str(self.config.project_root.resolve())
        entrypoint = str((bundle.path / job.entrypoint).resolve())
        if request.launch_mode.detach:
            with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
                proc = subprocess.Popen(
                    ["bash", entrypoint],
                    cwd=str(self.config.project_root),
                    env=env,
                    stdout=out,
                    stderr=err,
                    start_new_session=True,
                )
            handle = RunHandle(
                runtime_kind="local_host_process",
                run_id=str(proc.pid),
                target_id="local",
                bundle_path=str(bundle.path),
                metadata=LocalHostRunMetadata(
                    pid=proc.pid,
                    detach=True,
                    project_root=str(self.config.project_root.resolve()),
                    bundle_root=str(bundle.path.resolve()),
                    entrypoint=job.entrypoint,
                ),
            )
            bundle.write_run_handle(handle)
            bundle.write_run_status(RunStatus(runtime_kind="local_host_process", run_id=handle.run_id, state=RunState.RUNNING, metadata={"pid": proc.pid}))
            return handle

        with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
            proc = subprocess.run(["bash", entrypoint], cwd=str(self.config.project_root), env=env, stdout=out, stderr=err)
        _write_result(bundle, proc.returncode)
        handle = RunHandle(
            runtime_kind="local_host_process",
            run_id="foreground",
            target_id="local",
            bundle_path=str(bundle.path),
            metadata=LocalHostRunMetadata(
                pid=0,
                detach=False,
                project_root=str(self.config.project_root.resolve()),
                bundle_root=str(bundle.path.resolve()),
                entrypoint=job.entrypoint,
            ),
        )
        bundle.write_run_handle(handle)
        bundle.write_run_status(
            RunStatus(
                runtime_kind="local_host_process",
                run_id=handle.run_id,
                state=RunState.SUCCEEDED if proc.returncode == 0 else RunState.FAILED,
                metadata={"exit_code": proc.returncode},
            )
        )
        bundle.record_local_artifacts()
        return handle

    async def status(self, request: RunStatusRequest) -> RunStatus:
        handle = request.handle
        metadata = handle.metadata
        if not isinstance(metadata, LocalHostRunMetadata):
            raise ValueError("Local host run handle missing LocalHostRunMetadata")
        bundle = JobBundle(handle.bundle_path)
        result = _read_json_if_exists(_local_result_path(bundle))
        if result:
            state = RunState(result.get("state", "failed"))
            return RunStatus(runtime_kind="local_host_process", run_id=handle.run_id, state=state, metadata=result)
        if metadata.pid:
            try:
                os.kill(metadata.pid, 0)
            except OSError:
                return RunStatus(runtime_kind="local_host_process", run_id=handle.run_id, state=RunState.FAILED, detail="process not found")
            return RunStatus(runtime_kind="local_host_process", run_id=handle.run_id, state=RunState.RUNNING, metadata={"pid": metadata.pid})
        return RunStatus(runtime_kind="local_host_process", run_id=handle.run_id, state=RunState.FAILED, detail="no recorded pid")

    async def logs(self, request: RunLogsRequest) -> str:
        return _tail_local_logs(JobBundle(request.handle.bundle_path), request.tail)

    async def collect(self, request: CollectArtifactsRequest) -> ArtifactManifest:
        return JobBundle(request.handle.bundle_path).record_local_artifacts()

    async def terminate(self, request: TerminateRunRequest) -> None:
        metadata = request.handle.metadata
        if not isinstance(metadata, LocalHostRunMetadata):
            raise ValueError("Local host run handle missing LocalHostRunMetadata")
        if metadata.pid:
            try:
                os.killpg(metadata.pid, signal.SIGTERM)
            except OSError:
                pass


class LocalDockerRuntime:
    def __init__(self, config: ForgeConfig):
        self.config = config

    async def run(self, request: ExecutionRequest) -> RunHandle:
        if request.placement.kind != PlacementKind.LOCAL or request.launch_mode.kind != LaunchModeKind.DOCKER_IMAGE:
            raise ValueError("LocalDockerRuntime requires local + docker_image")
        bundle = JobBundle(request.bundle_path)
        job = bundle.load_job()
        image_name = request.launch_mode.image or self.config.default_exec_image
        container_name = _safe_name(job.job_id, "forge-worker")
        project_root = str(self.config.project_root.resolve())
        bundle_root = str(bundle.path.resolve())
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
        if not request.launch_mode.detach:
            cmd.append("--rm")
        if request.launch_mode.detach:
            cmd.append("-d")
        for key, value in _runtime_env(self.config, bundle, request).items():
            cmd.extend(["-e", f"{key}={value}"])
        cmd.extend([image_name, "bash", "-lc", _docker_bundle_wrapper()])
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            bundle.record_local_artifacts()
            detail = "\n".join(part for part in [proc.stderr, proc.stdout, _tail_local_logs(bundle, 200)] if part).strip()
            raise RuntimeError(detail or "Local docker runtime failed")
        handle = RunHandle(
            runtime_kind="local_docker_image",
            run_id=proc.stdout.strip() if request.launch_mode.detach else container_name,
            target_id="local",
            bundle_path=str(bundle.path),
            metadata=LocalDockerRunMetadata(container_name=container_name, image=image_name, detach=request.launch_mode.detach),
        )
        bundle.write_run_handle(handle)
        if not request.launch_mode.detach:
            result = _read_json_if_exists(_local_result_path(bundle))
            state = RunState(result.get("state", "succeeded" if proc.returncode == 0 else "failed"))
            bundle.write_run_status(
                RunStatus(
                    runtime_kind="local_docker_image",
                    run_id=handle.run_id,
                    state=state,
                    metadata={"exit_code": result.get("exit_code", proc.returncode)},
                )
            )
            bundle.record_local_artifacts()
        return handle

    async def status(self, request: RunStatusRequest) -> RunStatus:
        handle = request.handle
        metadata = handle.metadata
        if not isinstance(metadata, LocalDockerRunMetadata):
            raise ValueError("Local docker run handle missing LocalDockerRunMetadata")
        bundle = JobBundle(handle.bundle_path)
        result = _read_json_if_exists(_local_result_path(bundle))
        if result:
            state = RunState(result.get("state", "failed"))
            return RunStatus(runtime_kind="local_docker_image", run_id=handle.run_id, state=state, metadata={"container_name": metadata.container_name, **result})
        proc = subprocess.run(["docker", "inspect", "-f", "{{.State.Status}}", metadata.container_name], capture_output=True, text=True)
        if proc.returncode != 0:
            return RunStatus(runtime_kind="local_docker_image", run_id=handle.run_id, state=RunState.FAILED, detail=proc.stderr.strip())
        raw = proc.stdout.strip().lower()
        state = {"created": RunState.STARTING, "running": RunState.RUNNING, "exited": RunState.FAILED, "dead": RunState.FAILED}.get(raw, RunState.SUBMITTED)
        return RunStatus(runtime_kind="local_docker_image", run_id=handle.run_id, state=state, detail=raw, metadata={"container_name": metadata.container_name})

    async def logs(self, request: RunLogsRequest) -> str:
        metadata = request.handle.metadata
        if not isinstance(metadata, LocalDockerRunMetadata):
            raise ValueError("Local docker run handle missing LocalDockerRunMetadata")
        proc = subprocess.run(["docker", "logs", "--tail", str(request.tail), metadata.container_name], capture_output=True, text=True)
        output = (proc.stdout + proc.stderr).strip()
        if proc.returncode == 0 and output:
            return output
        return _tail_local_logs(JobBundle(request.handle.bundle_path), request.tail) or output

    async def collect(self, request: CollectArtifactsRequest) -> ArtifactManifest:
        return JobBundle(request.handle.bundle_path).record_local_artifacts()

    async def terminate(self, request: TerminateRunRequest) -> None:
        metadata = request.handle.metadata
        if not isinstance(metadata, LocalDockerRunMetadata):
            raise ValueError("Local docker run handle missing LocalDockerRunMetadata")
        subprocess.run(["docker", "rm", "-f", metadata.container_name], capture_output=True, text=True)


class TargonRentalDockerRuntime:
    def __init__(self, config: ForgeConfig):
        self.config = config
        self.backend = SshBackend(str(config.machines_file))

    async def _resolve_target(self, target: str) -> GpuInstance:
        instances = await self.backend.list_instances()
        for instance in instances:
            if instance.id == target or instance.host == target:
                return instance
        raise ValueError(f"Unknown Targon rental target: {target}")

    async def run(self, request: ExecutionRequest) -> RunHandle:
        if request.placement.kind != PlacementKind.TARGON_RENTAL or request.launch_mode.kind != LaunchModeKind.DOCKER_IMAGE:
            raise ValueError("TargonRentalDockerRuntime requires targon_rental + docker_image")
        if not request.placement.target:
            raise ValueError("Targon rental runtime requires --target")
        bundle = JobBundle(request.bundle_path)
        job = bundle.load_job()
        runtime_image = request.launch_mode.image or self.config.default_exec_image
        instance = await self._resolve_target(request.placement.target)
        workspace = _bundle_remote_workspace(job.job_id)
        container_name = _safe_name(job.job_id, "forge-worker")
        staging_repo = _runtime_staging_repo(self.config)
        use_hf_staging = bool(staging_repo)
        project_archive_path, bundle_archive_path = _runtime_staging_paths(job.job_id)
        env_flags = " ".join(f"-e {shlex.quote(f'{key}={value}')}" for key, value in _runtime_env(self.config, bundle, request).items())
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
            project_tgz = create_project_snapshot(self.config, os.path.join(tmp, "project.tar.gz"), include_affinetes=(job.kind.value == "eval"))
            bundle_tgz = create_bundle_archive(bundle, os.path.join(tmp, "bundle.tar.gz"))
            await self.backend.exec(instance, f"rm -rf {workspace} && mkdir -p {workspace}/project {workspace}/bundle {workspace}/data", timeout=_RENTAL_SSH_PREP_TIMEOUT)
            if use_hf_staging:
                _upload_runtime_archive(project_tgz, staging_repo, project_archive_path, self.config.hf_token)
                _upload_runtime_archive(bundle_tgz, staging_repo, bundle_archive_path, self.config.hf_token)
            else:
                await self.backend.upload(instance, project_tgz, f"{workspace}/project.tar.gz")
                await self.backend.upload(instance, bundle_tgz, f"{workspace}/bundle.tar.gz")
            docker_mode_flag = "-d" if request.launch_mode.detach else "--rm"
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
            rc, out, err = await self.backend.exec(instance, f"bash -lc {shlex.quote(remote_script)}", timeout=3600)
            if rc != 0:
                raise RuntimeError((err or out or "Targon rental runtime failed").strip())
        handle = RunHandle(
            runtime_kind="targon_rental_docker_image",
            run_id=container_name,
            target_id=instance.id,
            bundle_path=str(bundle.path),
            metadata=TargonRentalDockerRunMetadata(
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
                runtime_kind="targon_rental_docker_image",
                run_id=handle.run_id,
                state=RunState.SUBMITTED,
                metadata={"target": instance.id, "host": instance.host or "", "container_name": container_name},
            )
        )
        return handle

    async def status(self, request: RunStatusRequest) -> RunStatus:
        handle = request.handle
        metadata = handle.metadata
        if not isinstance(metadata, TargonRentalDockerRunMetadata):
            raise ValueError("Targon docker run handle missing TargonRentalDockerRunMetadata")
        instance = await self._resolve_target(metadata.target or handle.target_id)
        rc, out, _ = await self.backend.exec(instance, f"test -f {metadata.workspace}/bundle/runtime/result.json && cat {metadata.workspace}/bundle/runtime/result.json || true", timeout=_RENTAL_SSH_QUERY_TIMEOUT)
        result = {}
        if rc == 0 and out.strip():
            result = json.loads(out.strip())
        if result:
            state = RunState(result.get("state", "failed"))
            return RunStatus(runtime_kind="targon_rental_docker_image", run_id=handle.run_id, state=state, metadata={"container_name": metadata.container_name, "host": instance.host or "", **result})
        rc, out, err = await self.backend.exec(instance, f"docker inspect -f '{{{{.State.Status}}}}' {metadata.container_name}", timeout=_RENTAL_SSH_QUERY_TIMEOUT)
        if rc != 0:
            return RunStatus(runtime_kind="targon_rental_docker_image", run_id=handle.run_id, state=RunState.FAILED, detail=(err or out).strip())
        raw = out.strip().lower()
        state = {"created": RunState.STARTING, "restarting": RunState.STARTING, "running": RunState.RUNNING, "exited": RunState.FAILED, "dead": RunState.FAILED}.get(raw, RunState.SUBMITTED)
        return RunStatus(runtime_kind="targon_rental_docker_image", run_id=handle.run_id, state=state, detail=raw, metadata={"container_name": metadata.container_name, "host": instance.host or "", "target": instance.id})

    async def logs(self, request: RunLogsRequest) -> str:
        metadata = request.handle.metadata
        if not isinstance(metadata, TargonRentalDockerRunMetadata):
            raise ValueError("Targon docker run handle missing TargonRentalDockerRunMetadata")
        instance = await self._resolve_target(metadata.target or request.handle.target_id)
        rc, out, err = await self.backend.exec(instance, f"docker logs --tail {request.tail} {metadata.container_name}", timeout=_RENTAL_SSH_QUERY_TIMEOUT)
        output = (out + err).strip()
        if rc == 0 and output:
            return output
        rc, out, err = await self.backend.exec(
            instance,
            (f"for path in {metadata.workspace}/bundle/artifacts/stdout.log {metadata.workspace}/bundle/artifacts/stderr.log; do "
             "if [ -f \"$path\" ]; then tail -n "
             f"{request.tail} \"$path\"; fi; done"),
            timeout=_RENTAL_SSH_QUERY_TIMEOUT,
        )
        fallback = (out + err).strip()
        return fallback or output

    async def collect(self, request: CollectArtifactsRequest) -> ArtifactManifest:
        metadata = request.handle.metadata
        if not isinstance(metadata, TargonRentalDockerRunMetadata):
            raise ValueError("Targon docker run handle missing TargonRentalDockerRunMetadata")
        bundle = JobBundle(request.handle.bundle_path)
        instance = await self._resolve_target(metadata.target or request.handle.target_id)
        await self.backend.download(instance, f"{metadata.workspace}/bundle/artifacts", str(bundle.path))
        await self.backend.download(instance, f"{metadata.workspace}/bundle/runtime", str(bundle.path))
        return bundle.record_local_artifacts()

    async def terminate(self, request: TerminateRunRequest) -> None:
        metadata = request.handle.metadata
        if not isinstance(metadata, TargonRentalDockerRunMetadata):
            raise ValueError("Targon docker run handle missing TargonRentalDockerRunMetadata")
        instance = await self._resolve_target(metadata.target or request.handle.target_id)
        await self.backend.exec(instance, f"docker rm -f {metadata.container_name} >/dev/null 2>&1 || true; rm -rf {metadata.workspace}", timeout=_RENTAL_SSH_QUERY_TIMEOUT)
