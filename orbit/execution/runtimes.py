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

from orbit.compute.base import GpuInstance
from orbit.compute.ssh import SshBackend
from orbit.config import OrbitConfig
from orbit.execution.bundle import JobBundle
from orbit.execution.contracts import (
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
    TargonRentalHostRunMetadata,
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


def _bundle_archive_filter(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    name = info.name.rstrip("/")
    if name.startswith("bundle/runtime"):
        return None
    if name.startswith("bundle/artifacts") and name not in {"bundle/artifacts", "bundle/artifacts/manifest.json"}:
        return None
    if name.startswith("bundle/") and name.count("/") == 1 and name.endswith(".json") and name != "bundle/job.json":
        return None
    return info


def create_project_snapshot(config: OrbitConfig, output_path: str, include_affinetes: bool = False) -> str:
    root = config.project_root
    include = ["orbit", "scripts", "synth_config.json"]
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
    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(bundle.path, arcname="bundle", filter=_bundle_archive_filter)
    return output_path


def _bundle_remote_workspace(job_id: str) -> str:
    return f"/root/orbit-execution/{job_id}"


def _runtime_staging_repo(config: OrbitConfig) -> str:
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
        "source /opt/affine-venv/bin/activate >/dev/null 2>&1 || true && "
        "export PATH=/usr/local/cuda/bin:${PATH} LD_LIBRARY_PATH=/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-} HF_HOME=/data/.cache/huggingface TRANSFORMERS_CACHE=/data/.cache/huggingface/hub && "
        "export BUNDLE_ROOT=/workspace/bundle PROJECT_ROOT=/workspace/project PYTHONPATH=/workspace/project:${PYTHONPATH:-} ORBIT_PYTHON=/opt/affine-venv/bin/python ORBIT_SKIP_DOTENV=1 && "
        "bash scripts/entrypoint.sh > artifacts/stdout.log 2> artifacts/stderr.log; "
        "rc=$?; "
        "if [ \"$rc\" -eq 0 ]; then state=succeeded; else state=failed; fi; "
        "printf '{\"state\":\"%s\",\"exit_code\":%s}\\n' \"$state\" \"$rc\" > runtime/result.json; "
        "exit \"$rc\""
    )


def _docker_runtime_flags(request: ExecutionRequest) -> list[str]:
    flags: list[str] = []
    if request.resources.gpu_count and request.resources.gpu_count > 1:
        flags.extend(["--ipc=host"])
    return flags


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
        "source /opt/affine-venv/bin/activate >/dev/null 2>&1 || true\n"
        "export PATH=/usr/local/cuda/bin:${PATH} LD_LIBRARY_PATH=/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-} HF_HOME=/data/.cache/huggingface TRANSFORMERS_CACHE=/data/.cache/huggingface/hub\n"
        f"export BUNDLE_ROOT={bundle_root} PROJECT_ROOT={project_root} PYTHONPATH={project_root}:${{PYTHONPATH:-}} ORBIT_PYTHON=/opt/affine-venv/bin/python ORBIT_SKIP_DOTENV=1\n"
        "bash scripts/entrypoint.sh > artifacts/stdout.log 2> artifacts/stderr.log\n"
        "rc=$?\n"
        "if [ \"$rc\" -eq 0 ]; then state=succeeded; else state=failed; fi\n"
        "printf '{\"state\":\"%s\",\"exit_code\":%s}\\n' \"$state\" \"$rc\" > runtime/result.json\n"
        "exit \"$rc\"\n"
    )


def _remote_host_wrapper() -> str:
    return (
        "set -euo pipefail\n"
        "mkdir -p \"$WORKSPACE/project\" \"$WORKSPACE/bundle\" \"$WORKSPACE/downloads\" /data\n"
        "cp \"$WORKSPACE/project.tar.gz\" \"$WORKSPACE/downloads/project.tar.gz\"\n"
        "cp \"$WORKSPACE/bundle.tar.gz\" \"$WORKSPACE/downloads/bundle.tar.gz\"\n"
        "tar -xzf \"$WORKSPACE/downloads/project.tar.gz\" -C \"$WORKSPACE\"\n"
        "tar -xzf \"$WORKSPACE/downloads/bundle.tar.gz\" -C \"$WORKSPACE\"\n"
        "cd \"$WORKSPACE/bundle\"\n"
        "mkdir -p artifacts runtime\n"
        "source /opt/affine-venv/bin/activate >/dev/null 2>&1 || true\n"
        "export PATH=/usr/local/cuda/bin:${PATH} LD_LIBRARY_PATH=/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-} HF_HOME=/data/.cache/huggingface TRANSFORMERS_CACHE=/data/.cache/huggingface/hub\n"
        "export BUNDLE_ROOT=\"$WORKSPACE/bundle\" PROJECT_ROOT=\"$WORKSPACE/project\" PYTHONPATH=\"$WORKSPACE/project:${PYTHONPATH:-}\" ORBIT_PYTHON=/opt/affine-venv/bin/python ORBIT_SKIP_DOTENV=1\n"
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


def _runtime_env(config: OrbitConfig, bundle: JobBundle, request: ExecutionRequest) -> dict[str, str]:
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


def _append_runtime_log(bundle: JobBundle, message: str) -> None:
    bundle.append_runtime_log(message)


class LocalHostProcessRuntime:
    def __init__(self, config: OrbitConfig):
        self.config = config

    async def run(self, request: ExecutionRequest) -> RunHandle:
        if request.placement.kind != PlacementKind.LOCAL or request.launch_mode.kind != LaunchModeKind.HOST_PROCESS:
            raise ValueError("LocalHostProcessRuntime requires local + host_process")
        bundle = JobBundle(request.bundle_path)
        job = bundle.load_job()
        bundle.ensure_structure()
        _append_runtime_log(bundle, f"run start placement=local launch_mode=host_process detach={request.launch_mode.detach} entrypoint={job.entrypoint}")
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
            _append_runtime_log(bundle, f"run detached pid={proc.pid}")
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
        _append_runtime_log(bundle, f"run foreground exit_code={proc.returncode}")
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
            _append_runtime_log(bundle, f"status resolved_from=result state={state.value} run_id={handle.run_id}")
            return RunStatus(runtime_kind="local_host_process", run_id=handle.run_id, state=state, metadata=result)
        if metadata.pid:
            try:
                os.kill(metadata.pid, 0)
            except OSError:
                _append_runtime_log(bundle, f"status pid_missing pid={metadata.pid} run_id={handle.run_id}")
                return RunStatus(runtime_kind="local_host_process", run_id=handle.run_id, state=RunState.FAILED, detail="process not found")
            _append_runtime_log(bundle, f"status pid_alive pid={metadata.pid} run_id={handle.run_id}")
            return RunStatus(runtime_kind="local_host_process", run_id=handle.run_id, state=RunState.RUNNING, metadata={"pid": metadata.pid})
        _append_runtime_log(bundle, f"status no_recorded_pid run_id={handle.run_id}")
        return RunStatus(runtime_kind="local_host_process", run_id=handle.run_id, state=RunState.FAILED, detail="no recorded pid")

    async def logs(self, request: RunLogsRequest) -> str:
        bundle = JobBundle(request.handle.bundle_path)
        _append_runtime_log(bundle, f"logs tail={request.tail} run_id={request.handle.run_id}")
        return _tail_local_logs(bundle, request.tail)

    async def collect(self, request: CollectArtifactsRequest) -> ArtifactManifest:
        bundle = JobBundle(request.handle.bundle_path)
        _append_runtime_log(bundle, f"collect run_id={request.handle.run_id}")
        return bundle.record_local_artifacts()

    async def terminate(self, request: TerminateRunRequest) -> None:
        metadata = request.handle.metadata
        if not isinstance(metadata, LocalHostRunMetadata):
            raise ValueError("Local host run handle missing LocalHostRunMetadata")
        bundle = JobBundle(request.handle.bundle_path)
        _append_runtime_log(bundle, f"terminate run_id={request.handle.run_id} pid={metadata.pid}")
        if metadata.pid:
            try:
                os.killpg(metadata.pid, signal.SIGTERM)
            except OSError:
                pass


class LocalDockerRuntime:
    def __init__(self, config: OrbitConfig):
        self.config = config

    async def run(self, request: ExecutionRequest) -> RunHandle:
        if request.placement.kind != PlacementKind.LOCAL or request.launch_mode.kind != LaunchModeKind.DOCKER_IMAGE:
            raise ValueError("LocalDockerRuntime requires local + docker_image")
        bundle = JobBundle(request.bundle_path)
        job = bundle.load_job()
        _append_runtime_log(bundle, f"run start placement=local launch_mode=docker_image detach={request.launch_mode.detach} image={request.launch_mode.image or self.config.default_exec_image}")
        image_name = request.launch_mode.image or self.config.default_exec_image
        container_name = _safe_name(job.job_id, "orbit-worker")
        project_root = str(self.config.project_root.resolve())
        bundle_root = str(bundle.path.resolve())
        data_root = bundle.path / "runtime" / "data"
        data_root.mkdir(parents=True, exist_ok=True)
        cmd = [
            "docker",
            "run",
            "--name",
            container_name,
            "--entrypoint",
            "bash",
            "-v",
            f"{project_root}:/workspace/project",
            "-v",
            f"{bundle_root}:/workspace/bundle",
            "-v",
            f"{data_root.resolve()}:/data",
            "-w",
            "/workspace/project",
        ]
        cmd.extend(_docker_runtime_flags(request))
        if not request.launch_mode.detach:
            cmd.append("--rm")
        if request.launch_mode.detach:
            cmd.append("-d")
        for key, value in _runtime_env(self.config, bundle, request).items():
            cmd.extend(["-e", f"{key}={value}"])
        cmd.extend([image_name, "-lc", _docker_bundle_wrapper()])
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            _append_runtime_log(bundle, f"run docker_failed image={image_name} exit_code={proc.returncode}")
            bundle.record_local_artifacts()
            detail = "\n".join(part for part in [proc.stderr, proc.stdout, _tail_local_logs(bundle, 200)] if part).strip()
            raise RuntimeError(detail or "Local docker runtime failed")
        _append_runtime_log(bundle, f"run docker_submitted container={container_name} detach={request.launch_mode.detach}")
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
            _append_runtime_log(bundle, f"run docker_foreground_complete container={container_name} state={state.value}")
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
            _append_runtime_log(bundle, f"status docker_result state={state.value} container={metadata.container_name}")
            return RunStatus(runtime_kind="local_docker_image", run_id=handle.run_id, state=state, metadata={"container_name": metadata.container_name, **result})
        proc = subprocess.run(["docker", "inspect", "-f", "{{.State.Status}}", metadata.container_name], capture_output=True, text=True)
        if proc.returncode != 0:
            _append_runtime_log(bundle, f"status docker_inspect_failed container={metadata.container_name} exit_code={proc.returncode}")
            return RunStatus(runtime_kind="local_docker_image", run_id=handle.run_id, state=RunState.FAILED, detail=proc.stderr.strip())
        raw = proc.stdout.strip().lower()
        state = {"created": RunState.STARTING, "running": RunState.RUNNING, "exited": RunState.FAILED, "dead": RunState.FAILED}.get(raw, RunState.SUBMITTED)
        _append_runtime_log(bundle, f"status docker_inspect state={state.value} raw={raw} container={metadata.container_name}")
        return RunStatus(runtime_kind="local_docker_image", run_id=handle.run_id, state=state, detail=raw, metadata={"container_name": metadata.container_name})

    async def logs(self, request: RunLogsRequest) -> str:
        metadata = request.handle.metadata
        if not isinstance(metadata, LocalDockerRunMetadata):
            raise ValueError("Local docker run handle missing LocalDockerRunMetadata")
        bundle = JobBundle(request.handle.bundle_path)
        _append_runtime_log(bundle, f"logs docker tail={request.tail} container={metadata.container_name}")
        proc = subprocess.run(["docker", "logs", "--tail", str(request.tail), metadata.container_name], capture_output=True, text=True)
        output = (proc.stdout + proc.stderr).strip()
        if proc.returncode == 0 and output:
            return output
        return _tail_local_logs(bundle, request.tail) or output

    async def collect(self, request: CollectArtifactsRequest) -> ArtifactManifest:
        bundle = JobBundle(request.handle.bundle_path)
        metadata = request.handle.metadata
        container_name = metadata.container_name if isinstance(metadata, LocalDockerRunMetadata) else request.handle.run_id
        _append_runtime_log(bundle, f"collect docker container={container_name}")
        return bundle.record_local_artifacts()

    async def terminate(self, request: TerminateRunRequest) -> None:
        metadata = request.handle.metadata
        if not isinstance(metadata, LocalDockerRunMetadata):
            raise ValueError("Local docker run handle missing LocalDockerRunMetadata")
        bundle = JobBundle(request.handle.bundle_path)
        _append_runtime_log(bundle, f"terminate docker container={metadata.container_name}")
        subprocess.run(["docker", "rm", "-f", metadata.container_name], capture_output=True, text=True)


class TargonRentalDockerRuntime:
    def __init__(self, config: OrbitConfig):
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
        _append_runtime_log(bundle, f"run start placement=targon_rental launch_mode=docker_image target={request.placement.target} detach={request.launch_mode.detach}")
        runtime_image = request.launch_mode.image or self.config.default_exec_image
        instance = await self._resolve_target(request.placement.target)
        workspace = _bundle_remote_workspace(job.job_id)
        container_name = _safe_name(job.job_id, "orbit-worker")
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
            _append_runtime_log(bundle, f"run remote_prepare workspace={workspace} host={instance.host or ''}")
            await self.backend.exec(instance, f"rm -rf {workspace} && mkdir -p {workspace}/project {workspace}/bundle {workspace}/data", timeout=_RENTAL_SSH_PREP_TIMEOUT)
            if use_hf_staging:
                _append_runtime_log(bundle, f"run remote_stage hf repo={staging_repo}")
                _upload_runtime_archive(project_tgz, staging_repo, project_archive_path, self.config.hf_token)
                _upload_runtime_archive(bundle_tgz, staging_repo, bundle_archive_path, self.config.hf_token)
            else:
                _append_runtime_log(bundle, f"run remote_stage ssh host={instance.host or ''}")
                await self.backend.upload(instance, project_tgz, f"{workspace}/project.tar.gz")
                await self.backend.upload(instance, bundle_tgz, f"{workspace}/bundle.tar.gz")
            docker_mode_flag = "-d" if request.launch_mode.detach else "--rm"
            docker_runtime_flags = " ".join(_docker_runtime_flags(request))
            remote_script = (
                "set -euo pipefail; "
                f"docker rm -f {container_name} >/dev/null 2>&1 || true; "
                f"docker pull {runtime_image}; "
                f"docker run --gpus all --name {container_name} {docker_mode_flag} {docker_runtime_flags} --entrypoint bash "
                f"-v {workspace}:/staging "
                f"-v {workspace}/project:/workspace/project "
                f"-v {workspace}/bundle:/workspace/bundle "
                f"-v {workspace}/data:/data "
                f"-w /workspace/project "
                f"{env_flags} "
                f"{staging_env_flags} "
                f"{runtime_image} "
                f"-lc {shlex.quote(wrapper)}"
            )
            rc, out, err = await self.backend.exec(instance, f"bash -lc {shlex.quote(remote_script)}", timeout=3600)
            if rc != 0:
                _append_runtime_log(bundle, f"run remote_docker_failed container={container_name} exit_code={rc}")
                raise RuntimeError((err or out or "Targon rental runtime failed").strip())
        _append_runtime_log(bundle, f"run remote_docker_submitted container={container_name} workspace={workspace}")
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
        bundle = JobBundle(handle.bundle_path)
        rc, out, _ = await self.backend.exec(instance, f"test -f {metadata.workspace}/bundle/runtime/result.json && cat {metadata.workspace}/bundle/runtime/result.json || true", timeout=_RENTAL_SSH_QUERY_TIMEOUT)
        result = {}
        if rc == 0 and out.strip():
            result = json.loads(out.strip())
        if result:
            state = RunState(result.get("state", "failed"))
            _append_runtime_log(bundle, f"status remote_docker_result state={state.value} container={metadata.container_name}")
            return RunStatus(runtime_kind="targon_rental_docker_image", run_id=handle.run_id, state=state, metadata={"container_name": metadata.container_name, "host": instance.host or "", **result})
        rc, out, err = await self.backend.exec(instance, f"docker inspect -f '{{{{.State.Status}}}}' {metadata.container_name}", timeout=_RENTAL_SSH_QUERY_TIMEOUT)
        if rc != 0:
            _append_runtime_log(bundle, f"status remote_docker_inspect_failed container={metadata.container_name} exit_code={rc}")
            return RunStatus(runtime_kind="targon_rental_docker_image", run_id=handle.run_id, state=RunState.FAILED, detail=(err or out).strip())
        raw = out.strip().lower()
        state = {"created": RunState.STARTING, "restarting": RunState.STARTING, "running": RunState.RUNNING, "exited": RunState.FAILED, "dead": RunState.FAILED}.get(raw, RunState.SUBMITTED)
        _append_runtime_log(bundle, f"status remote_docker_inspect state={state.value} raw={raw} container={metadata.container_name}")
        return RunStatus(runtime_kind="targon_rental_docker_image", run_id=handle.run_id, state=state, detail=raw, metadata={"container_name": metadata.container_name, "host": instance.host or "", "target": instance.id})

    async def logs(self, request: RunLogsRequest) -> str:
        metadata = request.handle.metadata
        if not isinstance(metadata, TargonRentalDockerRunMetadata):
            raise ValueError("Targon docker run handle missing TargonRentalDockerRunMetadata")
        instance = await self._resolve_target(metadata.target or request.handle.target_id)
        bundle = JobBundle(request.handle.bundle_path)
        _append_runtime_log(bundle, f"logs remote_docker tail={request.tail} container={metadata.container_name}")
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
        _append_runtime_log(bundle, f"collect remote_docker workspace={metadata.workspace} target={instance.id}")
        await self.backend.download(instance, f"{metadata.workspace}/bundle/artifacts", str(bundle.path))
        await self.backend.download(instance, f"{metadata.workspace}/bundle/runtime", str(bundle.path))
        return bundle.record_local_artifacts()

    async def terminate(self, request: TerminateRunRequest) -> None:
        metadata = request.handle.metadata
        if not isinstance(metadata, TargonRentalDockerRunMetadata):
            raise ValueError("Targon docker run handle missing TargonRentalDockerRunMetadata")
        instance = await self._resolve_target(metadata.target or request.handle.target_id)
        bundle = JobBundle(request.handle.bundle_path)
        _append_runtime_log(bundle, f"terminate remote_docker container={metadata.container_name} workspace={metadata.workspace}")
        await self.backend.exec(instance, f"docker rm -f {metadata.container_name} >/dev/null 2>&1 || true; rm -rf {metadata.workspace}", timeout=_RENTAL_SSH_QUERY_TIMEOUT)


class TargonRentalHostProcessRuntime:
    def __init__(self, config: OrbitConfig):
        self.config = config
        self.backend = SshBackend(str(config.machines_file))

    async def _resolve_target(self, target: str) -> GpuInstance:
        instances = await self.backend.list_instances()
        for instance in instances:
            if instance.id == target or instance.host == target:
                return instance
        raise ValueError(f"Unknown Targon rental target: {target}")

    async def run(self, request: ExecutionRequest) -> RunHandle:
        if request.placement.kind != PlacementKind.TARGON_RENTAL or request.launch_mode.kind != LaunchModeKind.HOST_PROCESS:
            raise ValueError("TargonRentalHostProcessRuntime requires targon_rental + host_process")
        if not request.placement.target:
            raise ValueError("Targon rental runtime requires --target")
        bundle = JobBundle(request.bundle_path)
        job = bundle.load_job()
        _append_runtime_log(bundle, f"run start placement=targon_rental launch_mode=host_process target={request.placement.target} detach={request.launch_mode.detach}")
        instance = await self._resolve_target(request.placement.target)
        workspace = _bundle_remote_workspace(job.job_id)
        remote_runner = f"{workspace}/run.sh"
        with tempfile.TemporaryDirectory() as tmp:
            project_tgz = create_project_snapshot(self.config, os.path.join(tmp, "project.tar.gz"), include_affinetes=(job.kind.value == "eval"))
            bundle_tgz = create_bundle_archive(bundle, os.path.join(tmp, "bundle.tar.gz"))
            _append_runtime_log(bundle, f"run remote_prepare workspace={workspace} host={instance.host or ''}")
            await self.backend.exec(instance, f"rm -rf {workspace} && mkdir -p {workspace}", timeout=_RENTAL_SSH_PREP_TIMEOUT)
            await self.backend.upload(instance, project_tgz, f"{workspace}/project.tar.gz")
            await self.backend.upload(instance, bundle_tgz, f"{workspace}/bundle.tar.gz")
            runner_body = _remote_host_wrapper()
            runner_path = os.path.join(tmp, "run.sh")
            Path(runner_path).write_text(runner_body, encoding="utf-8")
            await self.backend.upload(instance, runner_path, remote_runner)
            env_pairs = _runtime_env(self.config, bundle, request)
            env_exports = " ".join(
                f"export {key}={shlex.quote(value)};"
                for key, value in env_pairs.items()
            )
            launch_prefix = f"set -euo pipefail; chmod +x {shlex.quote(remote_runner)}; export WORKSPACE={shlex.quote(workspace)}; {env_exports} "
            if request.launch_mode.detach:
                launch_script = launch_prefix + f"nohup bash {shlex.quote(remote_runner)} >/dev/null 2>&1 & echo $!"
            else:
                launch_script = launch_prefix + f"bash {shlex.quote(remote_runner)}"
            rc, out, err = await self.backend.exec(
                instance,
                launch_script,
                timeout=3600 if not request.launch_mode.detach else _RENTAL_SSH_PREP_TIMEOUT,
            )
            if rc != 0:
                _append_runtime_log(bundle, f"run remote_host_failed workspace={workspace} exit_code={rc}")
                raise RuntimeError((err or out or "Targon rental host runtime failed").strip())
        _append_runtime_log(bundle, f"run remote_host_submitted workspace={workspace} pid={(out or '').strip() or '0'}")
        pid = int((out or "0").strip() or "0") if request.launch_mode.detach else 0
        handle = RunHandle(
            runtime_kind="targon_rental_host_process",
            run_id=str(pid or job.job_id),
            target_id=instance.id,
            bundle_path=str(bundle.path),
            metadata=TargonRentalHostRunMetadata(
                target=instance.id,
                host=instance.host or "",
                workspace=workspace,
                pid=pid,
                detach=request.launch_mode.detach,
                entrypoint=job.entrypoint,
            ),
        )
        bundle.write_run_handle(handle)
        bundle.write_run_status(
            RunStatus(
                runtime_kind="targon_rental_host_process",
                run_id=handle.run_id,
                state=RunState.SUBMITTED if request.launch_mode.detach else RunState.SUCCEEDED,
                metadata={"target": instance.id, "host": instance.host or "", "pid": pid, **({"exit_code": 0} if not request.launch_mode.detach else {})},
            )
        )
        if not request.launch_mode.detach:
            bundle.record_local_artifacts()
        return handle

    async def status(self, request: RunStatusRequest) -> RunStatus:
        handle = request.handle
        metadata = handle.metadata
        if not isinstance(metadata, TargonRentalHostRunMetadata):
            raise ValueError("Targon host run handle missing TargonRentalHostRunMetadata")
        instance = await self._resolve_target(metadata.target or handle.target_id)
        bundle = JobBundle(handle.bundle_path)
        rc, out, _ = await self.backend.exec(
            instance,
            f"test -f {metadata.workspace}/bundle/runtime/result.json && cat {metadata.workspace}/bundle/runtime/result.json || true",
            timeout=_RENTAL_SSH_QUERY_TIMEOUT,
        )
        result = {}
        if rc == 0 and out.strip():
            result = json.loads(out.strip())
        if result:
            state = RunState(result.get("state", "failed"))
            _append_runtime_log(bundle, f"status remote_host_result state={state.value} pid={metadata.pid}")
            return RunStatus(
                runtime_kind="targon_rental_host_process",
                run_id=handle.run_id,
                state=state,
                metadata={"host": instance.host or "", "target": instance.id, **result},
            )
        if metadata.pid:
            rc, _, _ = await self.backend.exec(instance, f"kill -0 {metadata.pid}", timeout=_RENTAL_SSH_QUERY_TIMEOUT)
            if rc == 0:
                _append_runtime_log(bundle, f"status remote_host_alive pid={metadata.pid}")
                return RunStatus(
                    runtime_kind="targon_rental_host_process",
                    run_id=handle.run_id,
                    state=RunState.RUNNING,
                    metadata={"host": instance.host or "", "target": instance.id, "pid": metadata.pid},
                )
        _append_runtime_log(bundle, f"status remote_host_missing pid={metadata.pid}")
        return RunStatus(
            runtime_kind="targon_rental_host_process",
            run_id=handle.run_id,
            state=RunState.FAILED,
            detail="process not found",
            metadata={"host": instance.host or "", "target": instance.id, "pid": metadata.pid},
        )

    async def logs(self, request: RunLogsRequest) -> str:
        metadata = request.handle.metadata
        if not isinstance(metadata, TargonRentalHostRunMetadata):
            raise ValueError("Targon host run handle missing TargonRentalHostRunMetadata")
        instance = await self._resolve_target(metadata.target or request.handle.target_id)
        bundle = JobBundle(request.handle.bundle_path)
        _append_runtime_log(bundle, f"logs remote_host tail={request.tail} workspace={metadata.workspace}")
        remote_cmd = (
            "for path in "
            f"{metadata.workspace}/bundle/artifacts/stdout.log "
            f"{metadata.workspace}/bundle/artifacts/stderr.log "
            f"{metadata.workspace}/bundle/artifacts/training.log; do "
            "if [ -f \"$path\" ]; then tail -n "
            f"{request.tail} \"$path\"; fi; done"
        )
        rc, out, err = await self.backend.exec(instance, remote_cmd, timeout=_RENTAL_SSH_QUERY_TIMEOUT)
        return (out + err).strip()

    async def collect(self, request: CollectArtifactsRequest) -> ArtifactManifest:
        metadata = request.handle.metadata
        if not isinstance(metadata, TargonRentalHostRunMetadata):
            raise ValueError("Targon host run handle missing TargonRentalHostRunMetadata")
        bundle = JobBundle(request.handle.bundle_path)
        instance = await self._resolve_target(metadata.target or request.handle.target_id)
        _append_runtime_log(bundle, f"collect remote_host workspace={metadata.workspace} target={instance.id}")
        await self.backend.download(instance, f"{metadata.workspace}/bundle/artifacts", str(bundle.path))
        await self.backend.download(instance, f"{metadata.workspace}/bundle/runtime", str(bundle.path))
        return bundle.record_local_artifacts()

    async def terminate(self, request: TerminateRunRequest) -> None:
        metadata = request.handle.metadata
        if not isinstance(metadata, TargonRentalHostRunMetadata):
            raise ValueError("Targon host run handle missing TargonRentalHostRunMetadata")
        instance = await self._resolve_target(metadata.target or request.handle.target_id)
        bundle = JobBundle(request.handle.bundle_path)
        _append_runtime_log(bundle, f"terminate remote_host pid={metadata.pid} workspace={metadata.workspace}")
        commands = []
        if metadata.pid:
            commands.append(f"kill -TERM {metadata.pid} >/dev/null 2>&1 || true")
        commands.append(f"rm -rf {metadata.workspace}")
        await self.backend.exec(instance, "; ".join(commands), timeout=_RENTAL_SSH_QUERY_TIMEOUT)
