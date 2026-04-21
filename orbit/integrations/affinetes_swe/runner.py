"""Thin black-box runner around upstream affinetes SWE-INFINITE."""

from __future__ import annotations

import concurrent.futures
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from multiprocessing.connection import Client
from pathlib import Path
from typing import Any

from orbit.foundation.data_contracts import CollectResult

DEFAULT_AFFINETES_GIT_URL = "https://github.com/AffineFoundation/affinetes.git"
DEFAULT_SWE_CACHE_DIR = "/tmp/swe-infinite-cache"
DEFAULT_SHARED_RUNTIME_CACHE_ROOT = os.environ.get(
    "ORBIT_AFFINETES_SWE_RUNTIME_CACHE_ROOT",
    str(Path.home() / ".cache" / "orbit" / "affinetes_swe_runtime"),
)
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_TASK_FILE_RE = re.compile(r"^task_(\d{11})\.json$")


@dataclass(frozen=True)
class PreparedUpstreamRuntime:
    repo_root: Path
    env_dir: Path
    runtime_dir: Path
    runtime_home: Path
    python_bin: Path
    upstream_ref: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()) or "task"


def parse_task_range(spec: str) -> list[str]:
    values: list[str] = []
    for part in (spec or "").split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            step = 1 if end >= start else -1
            for number in range(start, end + step, step):
                values.append(str(number))
        else:
            values.append(token)
    return values


def _task_id_from_line(line: str) -> str:
    raw = line.strip()
    if not raw:
        return ""
    if raw.startswith("{"):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        for key in ("instance_id", "task_id", "_task_id"):
            value = payload.get(key)
            if value not in (None, ""):
                return str(value)
        return raw
    return raw


def load_task_ids(*, task_range: str = "", task_file: str = "") -> list[str]:
    values = parse_task_range(task_range)
    if task_file:
        path = Path(task_file)
        for line in path.read_text(encoding="utf-8").splitlines():
            task_id = _task_id_from_line(line)
            if task_id:
                values.append(task_id)
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    if not deduped:
        raise RuntimeError("Provide at least one task via --task-range or --task-file")
    return deduped


def _selected_tasks_from_manifest(path: str) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    tasks = payload.get("selected_tasks")
    if not isinstance(tasks, list) or not tasks:
        raise RuntimeError(f"selected_tasks manifest is empty or invalid: {path}")
    normalized: list[dict[str, Any]] = []
    for item in tasks:
        if not isinstance(item, dict):
            raise RuntimeError(f"selected_tasks entry is not an object: {item!r}")
        task_id = item.get("task_id")
        if task_id in (None, ""):
            raise RuntimeError(f"selected_tasks entry missing task_id: {item!r}")
        normalized.append(dict(item))
    return normalized


def _task_cache_filename(task_id: str | int) -> str:
    try:
        numeric = int(str(task_id))
    except ValueError as exc:
        raise RuntimeError(f"task_id must be numeric for cache lookup: {task_id!r}") from exc
    return f"task_{numeric:011d}.json"


def _load_task_payload(cache_dir: str, task_id: str | int) -> dict[str, Any]:
    path = Path(cache_dir) / _task_cache_filename(task_id)
    if not path.exists():
        raise RuntimeError(f"task cache missing for task_id {task_id}: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_task_image(task: dict[str, Any]) -> str:
    raw = str(task.get("dockerhub_tag") or "").strip()
    if not raw:
        raise RuntimeError("task missing dockerhub_tag")
    if "/" in raw and ":" in raw:
        return raw
    if ":" in raw:
        return f"affinefoundation/swe_infinite_images:{raw.split(':', 1)[1]}"
    return f"affinefoundation/swe_infinite_images:{raw}"


def _docker_image_present(image: str, *, timeout_secs: int = 120, retries: int = 2) -> bool:
    last_timeout: subprocess.TimeoutExpired | None = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            inspect = _run(["docker", "image", "inspect", image], timeout=timeout_secs)
        except subprocess.TimeoutExpired as exc:
            last_timeout = exc
            if attempt >= max(1, retries):
                raise
            time.sleep(min(2 * attempt, 5))
            continue
        return inspect.returncode == 0
    if last_timeout is not None:
        raise last_timeout
    return False


def _pull_task_image(
    *,
    image: str,
    timeout_secs: int,
    retries: int,
    inspect_timeout_secs: int = 120,
    inspect_retries: int = 2,
) -> dict[str, Any]:
    try:
        if _docker_image_present(image, timeout_secs=inspect_timeout_secs, retries=inspect_retries):
            return {"image": image, "status": "cached", "attempts": 0}
    except subprocess.TimeoutExpired as exc:
        return {
            "image": image,
            "status": "retryable_failed",
            "attempts": max(1, int(inspect_retries)),
            "error": str(exc)[:2000],
        }
    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            pull = _run(["docker", "pull", image], timeout=timeout_secs)
        except subprocess.TimeoutExpired as exc:
            last_error = str(exc)
            if attempt >= retries:
                return {
                    "image": image,
                    "status": "retryable_failed",
                    "attempts": attempt,
                    "error": last_error[:2000],
                }
            time.sleep(min(5 * attempt, 15))
            continue
        if pull.returncode == 0:
            return {"image": image, "status": "pulled", "attempts": attempt}
        last_error = (pull.stderr or pull.stdout or "").strip()
        time.sleep(min(5 * attempt, 15))
    return {"image": image, "status": "failed", "attempts": retries, "error": last_error[:2000]}


def prewarm_swe_task_images(
    *,
    selected_tasks_json: str,
    cache_dir: str,
    output_path: str,
    pull_timeout_secs: int = 1800,
    pull_concurrency: int = 4,
    pull_retries: int = 3,
) -> dict[str, Any]:
    selected = _selected_tasks_from_manifest(selected_tasks_json)
    images: dict[str, dict[str, Any]] = {}
    for item in selected:
        task = _load_task_payload(cache_dir, item["task_id"])
        image = _resolve_task_image(task)
        record = images.setdefault(image, {"image": image, "task_ids": [], "instance_ids": []})
        record["task_ids"].append(int(item["task_id"]))
        instance_id = str(item.get("instance_id") or "").strip()
        if instance_id:
            record["instance_ids"].append(instance_id)

    ordered_images = sorted(images)
    started_at = time.time()
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, int(pull_concurrency))) as pool:
        future_map = {
            pool.submit(
                _pull_task_image,
                image=image,
                timeout_secs=int(pull_timeout_secs),
                retries=max(1, int(pull_retries)),
            ): image
            for image in ordered_images
        }
        for future in concurrent.futures.as_completed(future_map):
            image = future_map[future]
            result = dict(images[image])
            result.update(future.result())
            results.append(result)

    results.sort(key=lambda item: item["image"])
    payload = {
        "selected_tasks_json": str(Path(selected_tasks_json).resolve()),
        "cache_dir": str(Path(cache_dir).resolve()),
        "pull_timeout_secs": int(pull_timeout_secs),
        "pull_concurrency": int(pull_concurrency),
        "pull_retries": int(pull_retries),
        "unique_image_count": len(ordered_images),
        "task_count": len(selected),
        "elapsed_secs": round(time.time() - started_at, 3),
        "images": results,
    }
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    failed = [item for item in results if item.get("status") == "failed"]
    if failed:
        failed_images = ", ".join(item["image"] for item in failed[:5])
        raise RuntimeError(f"task image prewarm failed for {len(failed)} images: {failed_images}")
    return payload


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _require_exact_ref(ref: str) -> str:
    normalized = str(ref or "").strip().lower()
    if not _COMMIT_RE.fullmatch(normalized):
        raise RuntimeError("upstream_ref must be an exact 40-character git commit")
    return normalized


def _git_head(repo_root: Path) -> str:
    proc = _run(["git", "rev-parse", "HEAD"], cwd=repo_root, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "git rev-parse HEAD failed")
    return proc.stdout.strip().lower()


def _ensure_clean(repo_root: Path) -> None:
    _cleanup_generated_python_artifacts(repo_root)
    proc = _run(["git", "status", "--porcelain"], cwd=repo_root, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "git status failed")
    if proc.stdout.strip():
        raise RuntimeError(f"upstream checkout is dirty: {repo_root}")


def _cleanup_generated_python_artifacts(repo_root: Path) -> None:
    for cache_dir in repo_root.rglob("__pycache__"):
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir, ignore_errors=True)
    for pyc in repo_root.rglob("*.pyc"):
        try:
            pyc.unlink()
        except FileNotFoundError:
            pass


def _clone_exact_ref(runtime_dir: Path, git_url: str, ref: str) -> Path:
    repo_root = runtime_dir / "affinetes"
    if repo_root.exists():
        current = _git_head(repo_root)
        _ensure_clean(repo_root)
        if current != ref:
            raise RuntimeError(f"existing cloned upstream repo is at {current}, expected {ref}")
        return repo_root

    repo_root.parent.mkdir(parents=True, exist_ok=True)
    init = _run(["git", "init", str(repo_root)], timeout=60)
    if init.returncode != 0:
        raise RuntimeError(init.stderr.strip() or init.stdout.strip() or "git init failed")
    remote = _run(["git", "remote", "add", "origin", git_url], cwd=repo_root, timeout=30)
    if remote.returncode != 0:
        raise RuntimeError(remote.stderr.strip() or remote.stdout.strip() or "git remote add failed")
    fetch = _run(["git", "fetch", "--depth", "1", "origin", ref], cwd=repo_root, timeout=300)
    if fetch.returncode != 0:
        raise RuntimeError(fetch.stderr.strip() or fetch.stdout.strip() or f"git fetch failed for {ref}")
    checkout = _run(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=repo_root, timeout=60)
    if checkout.returncode != 0:
        raise RuntimeError(checkout.stderr.strip() or checkout.stdout.strip() or f"git checkout failed for {ref}")
    current = _git_head(repo_root)
    if current != ref:
        raise RuntimeError(f"cloned upstream repo at {current}, expected {ref}")
    _ensure_clean(repo_root)
    return repo_root


def _ensure_requirements(python_bin: Path, requirements_path: Path, stamp_path: Path, ref: str) -> None:
    requirements_text = requirements_path.read_text(encoding="utf-8")
    version = _python_version(python_bin)
    stamp_value = json.dumps(
        {
            "ref": ref,
            "python": version,
            "requirements_sha256": hashlib.sha256(requirements_text.encode("utf-8")).hexdigest(),
        },
        sort_keys=True,
    )
    if stamp_path.exists() and stamp_path.read_text(encoding="utf-8") == stamp_value:
        return

    pip_probe = _run([str(python_bin), "-m", "pip", "--version"], timeout=120)
    if pip_probe.returncode != 0:
        ensurepip = _run([str(python_bin), "-m", "ensurepip", "--upgrade"], timeout=600)
        if ensurepip.returncode != 0:
            raise RuntimeError(
                ensurepip.stderr.strip()
                or ensurepip.stdout.strip()
                or "failed to bootstrap pip with ensurepip"
            )

    install = _run([str(python_bin), "-m", "pip", "install", "-r", str(requirements_path)], timeout=1800)
    if install.returncode != 0:
        raise RuntimeError(
            install.stderr.strip() or install.stdout.strip() or "failed to install upstream SWE requirements"
        )
    stamp_path.write_text(stamp_value, encoding="utf-8")


def _ensure_codex_static_binary(runtime_dir: Path, runtime_home: Path) -> None:
    alias_path = runtime_home / "codex-static"
    if alias_path.exists():
        return

    host_static = shutil.which("codex-static")
    if host_static:
        alias_path.symlink_to(host_static)
        return

    npm = shutil.which("npm")
    if not npm:
        return

    package_json = Path("/home/ubuntu/node-v24.13.0-linux-x64/lib/node_modules/@openai/codex/package.json")
    version = "0.121.0"
    if package_json.exists():
        try:
            version = str(json.loads(package_json.read_text(encoding="utf-8")).get("version") or version)
        except Exception:
            pass

    npm_root = runtime_dir / "npm-codex-static"
    binary_path = npm_root / "node_modules" / "@openai" / "codex-linux-x64" / "vendor" / "x86_64-unknown-linux-musl" / "codex" / "codex"
    if not binary_path.exists():
        npm_root.mkdir(parents=True, exist_ok=True)
        package_alias = f"@openai/codex-linux-x64@npm:@openai/codex@{version}-linux-x64"
        if not (npm_root / "package.json").exists():
            init = _run([npm, "init", "-y"], cwd=npm_root, timeout=120)
            if init.returncode != 0:
                raise RuntimeError(init.stderr.strip() or init.stdout.strip() or "failed to initialize npm workspace for codex-static")
        install = _run([npm, "install", package_alias], cwd=npm_root, timeout=600)
        if install.returncode != 0:
            raise RuntimeError(install.stderr.strip() or install.stdout.strip() or "failed to install codex-static platform package")
    if binary_path.exists():
        alias_path.symlink_to(binary_path)


def _python_version(python_bin: Path | str) -> str:
    proc = _run([str(python_bin), "-c", "import platform; print(platform.python_version())"], timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "failed to determine python version")
    return proc.stdout.strip()


def _shared_runtime_cache_key(*, ref: str, upstream_python: str, repo_root: Path) -> tuple[str, str]:
    requirements = repo_root / "environments" / "SWE-INFINITE" / "requirements.txt"
    requirements_text = requirements.read_text(encoding="utf-8")
    resolved_python = shutil.which(upstream_python) or upstream_python
    python_version = _python_version(resolved_python)
    key_material = json.dumps(
        {
            "ref": ref,
            "upstream_python": os.path.realpath(resolved_python),
            "python_version": python_version,
            "requirements_sha256": hashlib.sha256(requirements_text.encode("utf-8")).hexdigest(),
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(key_material.encode("utf-8")).hexdigest()[:24]
    return digest, python_version


@contextlib.contextmanager
def _file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _ensure_runtime_env(runtime_dir: Path, upstream_python: str, repo_root: Path, ref: str) -> tuple[Path, Path]:
    runtime_home = runtime_dir / "home"
    runtime_home.mkdir(parents=True, exist_ok=True)

    cache_root = Path(DEFAULT_SHARED_RUNTIME_CACHE_ROOT).expanduser().resolve()
    cache_key, python_version = _shared_runtime_cache_key(ref=ref, upstream_python=upstream_python, repo_root=repo_root)
    shared_root = cache_root / cache_key
    venv_dir = shared_root / "venv"
    python_bin = venv_dir / "bin" / "python"
    metadata_path = shared_root / "runtime.json"
    stamp = shared_root / "requirements.stamp"
    requirements = repo_root / "environments" / "SWE-INFINITE" / "requirements.txt"

    with _file_lock(cache_root / f"{cache_key}.lock"):
        if shared_root.exists() and not python_bin.exists():
            shutil.rmtree(shared_root, ignore_errors=True)
        shared_root.mkdir(parents=True, exist_ok=True)
        if not python_bin.exists():
            create = _run([upstream_python, "-m", "venv", str(venv_dir)], timeout=300)
            if create.returncode != 0:
                raise RuntimeError(create.stderr.strip() or create.stdout.strip() or "failed to create upstream venv")
        if not python_bin.exists():
            raise RuntimeError(f"missing venv python: {python_bin}")
        _ensure_requirements(python_bin, requirements, stamp, ref)
        metadata_path.write_text(
            json.dumps(
                {
                    "cache_key": cache_key,
                    "ref": ref,
                    "upstream_python": upstream_python,
                    "python_version": python_version,
                    "repo_root": str(repo_root),
                    "requirements_path": str(requirements),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    return python_bin, runtime_home


def prepare_upstream_runtime(
    *,
    output_dir: str,
    upstream_repo_path: str = "",
    upstream_git_url: str = DEFAULT_AFFINETES_GIT_URL,
    upstream_ref: str,
    upstream_python: str = "python3",
    ensure_codex_static: bool = False,
) -> PreparedUpstreamRuntime:
    ref = _require_exact_ref(upstream_ref)
    runtime_dir = Path(output_dir).resolve() / ".runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    if upstream_repo_path:
        repo_root = Path(upstream_repo_path).resolve()
        if not repo_root.exists():
            raise RuntimeError(f"upstream_repo_path does not exist: {repo_root}")
        current = _git_head(repo_root)
        _ensure_clean(repo_root)
        if current != ref:
            raise RuntimeError(f"upstream repo is at {current}, expected {ref}")
    else:
        repo_root = _clone_exact_ref(runtime_dir, upstream_git_url, ref)

    env_dir = repo_root / "environments" / "SWE-INFINITE"
    if not env_dir.exists():
        raise RuntimeError(f"missing SWE-INFINITE environment in upstream repo: {env_dir}")
    python_bin, runtime_home = _ensure_runtime_env(runtime_dir, upstream_python, repo_root, ref)
    if ensure_codex_static:
        _ensure_codex_static_binary(runtime_dir, runtime_home)
    return PreparedUpstreamRuntime(
        repo_root=repo_root,
        env_dir=env_dir,
        runtime_dir=runtime_dir,
        runtime_home=runtime_home,
        python_bin=python_bin,
        upstream_ref=ref,
    )


def _invoke_env(
    *,
    prepared: PreparedUpstreamRuntime,
    request: dict[str, Any],
    home_dir: Path,
    stdout_path: Path,
    stderr_path: Path,
    timeout: int,
) -> Path:
    orbit_root = _repo_root()
    request_path = stdout_path.parent / "invoke_request.json"
    result_path = stdout_path.parent / "invoke_result.json"
    request_payload = dict(request)
    request_payload["repo_root"] = str(prepared.repo_root)
    request_path.write_text(json.dumps(request_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    env = os.environ.copy()
    env["HOME"] = str(home_dir)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join(
        [str(orbit_root), str(prepared.repo_root), str(prepared.env_dir), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    try:
        proc = subprocess.run(
            [
                str(prepared.python_bin),
                str(_repo_root() / "orbit" / "integrations" / "affinetes_swe" / "invoke.py"),
                "--request-file",
                str(request_path),
                "--result-file",
                str(result_path),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        stdout_path.write_text(proc.stdout or "", encoding="utf-8")
        stderr_path.write_text(proc.stderr or "", encoding="utf-8")
        return {
            "result_path": str(result_path) if result_path.exists() else "",
            "returncode": proc.returncode,
            "error": (proc.stderr or proc.stdout or "").strip(),
        }
    except subprocess.TimeoutExpired as exc:
        timeout_stdout = exc.stdout or ""
        timeout_stderr = exc.stderr or ""
        if isinstance(timeout_stdout, bytes):
            timeout_stdout = timeout_stdout.decode("utf-8", errors="replace")
        if isinstance(timeout_stderr, bytes):
            timeout_stderr = timeout_stderr.decode("utf-8", errors="replace")
        stdout_path.write_text(str(timeout_stdout), encoding="utf-8")
        stderr_path.write_text(str(timeout_stderr), encoding="utf-8")
        return {
            "result_path": str(result_path) if result_path.exists() else "",
            "returncode": 124,
            "error": f"upstream invocation timed out after {timeout}s",
        }


def _summary_from_existing(result_path: Path) -> tuple[int, str]:
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    success = 1 if bool(payload.get("success")) else 0
    instance_id = str(payload.get("extra", {}).get("instance_id", "") or payload.get("task_id", "") or result_path.parent.name)
    return success, instance_id


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def run_affinetes_swe_evaluate(
    *,
    task_range: str = "",
    task_file: str = "",
    output_dir: str,
    upstream_repo_path: str = "",
    upstream_git_url: str = DEFAULT_AFFINETES_GIT_URL,
    upstream_ref: str,
    upstream_python: str = "python3",
    agent: str,
    workers: int = 1,
    resume: bool = False,
    model: str,
    api_base: str = "https://llm.chutes.ai/v1",
    api_key: str = "",
    cache_dir: str = DEFAULT_SWE_CACHE_DIR,
    timeout: int = 1800,
    collect_logprobs: bool = False,
) -> CollectResult:
    tasks = load_task_ids(task_range=task_range, task_file=task_file)
    prepared = prepare_upstream_runtime(
        output_dir=output_dir,
        upstream_repo_path=upstream_repo_path,
        upstream_git_url=upstream_git_url,
        upstream_ref=upstream_ref,
        upstream_python=upstream_python,
        ensure_codex_static=agent == "codex",
    )
    root = Path(output_dir).resolve()
    raw_root = root / "raw"
    manifest_path = root / "manifests" / "run.json"
    raw_root.mkdir(parents=True, exist_ok=True)

    def _run_one(task_id: str) -> dict[str, Any]:
        task_slug = _slug(task_id)
        task_dir = raw_root / task_slug
        task_dir.mkdir(parents=True, exist_ok=True)
        upstream_result_path = task_dir / "upstream_result.json"
        stdout_path = task_dir / "stdout.log"
        stderr_path = task_dir / "stderr.log"
        home_dir = prepared.runtime_dir / "home" / task_slug
        home_dir.mkdir(parents=True, exist_ok=True)
        shared_codex = prepared.runtime_home / "codex-static"
        task_codex = home_dir / "codex-static"
        if shared_codex.exists() and not task_codex.exists():
            task_codex.symlink_to(shared_codex)

        if resume and upstream_result_path.exists():
            success, instance_id = _summary_from_existing(upstream_result_path)
            return {
                "task_id": task_id,
                "instance_id": instance_id,
                "success": success,
                "resumed": True,
                "upstream_result": str(upstream_result_path),
                "stdout_log": str(stdout_path),
                "stderr_log": str(stderr_path),
                "conversation": str(task_dir / "conversation.json") if (task_dir / "conversation.json").exists() else "",
                "exit_code": 0,
            }

        invoke = _invoke_env(
            prepared=prepared,
            request={
                "mode": "evaluate",
                "task_id": task_id,
                "agent": agent,
                "model": model,
                "api_base": api_base,
                "api_key": api_key,
                "cache_dir": cache_dir,
                "timeout": timeout,
                "collect_logprobs": collect_logprobs,
            },
            home_dir=home_dir,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout=timeout + 60,
        )
        payload: dict[str, Any] = {}
        if invoke["result_path"]:
            payload = json.loads(Path(invoke["result_path"]).read_text(encoding="utf-8"))
            upstream_result_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        conversation_path = task_dir / "conversation.json"
        conversation = payload.get("extra", {}).get("conversation")
        if conversation is not None:
            conversation_path.write_text(json.dumps(conversation, indent=2, ensure_ascii=False), encoding="utf-8")
        return {
            "task_id": task_id,
            "instance_id": str(payload.get("extra", {}).get("instance_id", "") or task_id),
            "success": 1 if bool(payload.get("success")) else 0,
            "resumed": False,
            "upstream_result": str(upstream_result_path) if upstream_result_path.exists() else "",
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
            "conversation": str(conversation_path) if conversation is not None else "",
            "exit_code": int(invoke["returncode"]),
            "score": payload.get("score", 0.0),
            "error": str(invoke.get("error", "") or ""),
        }

    if workers <= 1 or len(tasks) == 1:
        task_entries = [_run_one(task_id) for task_id in tasks]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            task_entries = list(pool.map(_run_one, tasks))

    success_count = sum(int(entry.get("success", 0)) for entry in task_entries)
    manifest = {
        "schema_version": "affinetes_swe_blackbox_run.v1",
        "mode": "evaluate",
        "agent": agent,
        "task_count": len(task_entries),
        "success_count": success_count,
        "failure_count": len(task_entries) - success_count,
        "model": model,
        "api_base": api_base,
        "upstream_repo_path": str(prepared.repo_root),
        "upstream_git_url": upstream_git_url,
        "upstream_ref": prepared.upstream_ref,
        "upstream_python": str(prepared.python_bin),
        "cache_dir": cache_dir,
        "collect_logprobs": collect_logprobs,
        "raw_dir": str(raw_root),
        "tasks": task_entries,
        "command": {
            "mode": "evaluate",
            "agent": agent,
            "workers": workers,
            "resume": resume,
        },
    }
    _write_manifest(manifest_path, manifest)
    return CollectResult(
        output=str(manifest_path),
        staging_path=str(manifest_path),
        raw_path=str(raw_root),
        raw_files=[
            *[entry["upstream_result"] for entry in task_entries if entry.get("upstream_result")],
            *[entry["conversation"] for entry in task_entries if entry.get("conversation")],
        ],
        records=len(task_entries),
        success=success_count,
        failed=len(task_entries) - success_count,
    )


def _server_meta_path(output_dir: str) -> Path:
    return Path(output_dir).resolve() / ".runtime" / "openenv_server.json"


def _server_socket_path(output_dir: str) -> Path:
    digest = hashlib.sha256(str(Path(output_dir).resolve()).encode("utf-8")).hexdigest()[:16]
    return Path("/tmp") / f"orbit-openenv-{digest}.sock"


def _server_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _server_env(prepared: PreparedUpstreamRuntime, home_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(home_dir)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("ORBIT_OPENENV_ALLOW_STARTUP_STALE_CLEANUP", "false")
    env.setdefault("ORBIT_OPENENV_DOCKER_PULL_TIMEOUT_SECS", "1800")
    env.setdefault("ORBIT_OPENENV_DOCKER_PULL_RETRIES", "3")
    env.setdefault("ORBIT_OPENENV_DOCKER_PULL_RETRY_DELAY_SECS", "5")
    env.setdefault("ORBIT_OPENENV_DOCKER_RUN_TIMEOUT_SECS", "180")
    env.setdefault("ORBIT_OPENENV_DOCKER_RUN_RETRIES", "2")
    env.setdefault("ORBIT_OPENENV_DOCKER_RUN_RETRY_DELAY_SECS", "3")
    env["PYTHONPATH"] = os.pathsep.join(
        [str(_repo_root()), str(prepared.repo_root), str(prepared.env_dir), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    return env


def _ensure_openenv_server(
    *,
    output_dir: str,
    prepared: PreparedUpstreamRuntime,
    cache_dir: str,
    api_key: str,
) -> dict[str, Any]:
    meta_path = _server_meta_path(output_dir)
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if _server_pid_alive(int(meta.get("pid", 0))) and Path(meta["socket_path"]).exists():
            return meta
    runtime_home = prepared.runtime_dir / "home" / "openenv"
    runtime_home.mkdir(parents=True, exist_ok=True)
    raw_dir = Path(output_dir).resolve() / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    socket_path = _server_socket_path(output_dir)
    ready_path = prepared.runtime_dir / "openenv_ready.json"
    for stale in (socket_path, ready_path, meta_path):
        try:
            if stale.exists():
                stale.unlink()
        except FileNotFoundError:
            pass
    log_path = raw_dir / "openenv_server.log"
    env = _server_env(prepared, runtime_home)
    with log_path.open("a", encoding="utf-8") as handle:
        proc = subprocess.Popen(
            [
                str(prepared.python_bin),
                str(_repo_root() / "orbit" / "integrations" / "affinetes_swe" / "openenv_server.py"),
                "--repo-root",
                str(prepared.repo_root),
                "--socket-path",
                str(socket_path),
                "--ready-file",
                str(ready_path),
                "--cache-dir",
                cache_dir,
                "--api-key",
                api_key,
            ],
            stdout=handle,
            stderr=handle,
            env=env,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    deadline = time.time() + 60
    while time.time() < deadline:
        if ready_path.exists():
            meta = json.loads(ready_path.read_text(encoding="utf-8"))
            meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
            return meta
        time.sleep(0.2)
    proc.terminate()
    log_tail = ""
    if log_path.exists():
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            log_tail = "\n".join(lines[-40:])
        except Exception:
            log_tail = ""
    if log_tail:
        raise RuntimeError(f"openenv server did not become ready\n{log_tail}")
    raise RuntimeError("openenv server did not become ready")


def _openenv_call(output_dir: str, request: dict[str, Any]) -> dict[str, Any]:
    meta = json.loads(_server_meta_path(output_dir).read_text(encoding="utf-8"))
    conn = Client(meta["socket_path"], family="AF_UNIX")
    try:
        conn.send(request)
        return conn.recv()
    finally:
        conn.close()


def _write_openenv_response(output_dir: str, payload: dict[str, Any]) -> dict[str, Any]:
    raw_dir = Path(output_dir).resolve() / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    response_path = raw_dir / "openenv_last_response.json"
    response_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    session_path = raw_dir / "openenv_session.json"
    session = {}
    if session_path.exists():
        session = json.loads(session_path.read_text(encoding="utf-8"))
    if payload.get("episode_id"):
        session["last_episode_id"] = payload["episode_id"]
    if payload.get("checkpoint_id"):
        session["last_checkpoint_id"] = payload["checkpoint_id"]
    elif payload.get("latest_checkpoint_id"):
        session["last_checkpoint_id"] = payload["latest_checkpoint_id"]
    session["last_response_path"] = str(response_path)
    session_path.write_text(json.dumps(session, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def openenv_reset(
    *,
    output_dir: str,
    upstream_repo_path: str = "",
    upstream_git_url: str = DEFAULT_AFFINETES_GIT_URL,
    upstream_ref: str,
    upstream_python: str = "python3",
    cache_dir: str = DEFAULT_SWE_CACHE_DIR,
    api_key: str = "",
    task_id: str,
    seed: int | None = None,
    step_limit: int = 100,
    command_timeout: int = 300,
) -> dict[str, Any]:
    prepared = prepare_upstream_runtime(
        output_dir=output_dir,
        upstream_repo_path=upstream_repo_path,
        upstream_git_url=upstream_git_url,
        upstream_ref=upstream_ref,
        upstream_python=upstream_python,
    )
    _ensure_openenv_server(output_dir=output_dir, prepared=prepared, cache_dir=cache_dir, api_key=api_key)
    response = _openenv_call(
        output_dir,
        {
            "action": "reset",
            "task_id": task_id,
            "seed": seed,
            "step_limit": step_limit,
            "command_timeout": command_timeout,
        },
    )
    return _write_openenv_response(output_dir, response)


def _last_episode_id(output_dir: str) -> str:
    session_path = Path(output_dir).resolve() / "raw" / "openenv_session.json"
    if not session_path.exists():
        raise RuntimeError("no openenv session metadata found; run reset first")
    payload = json.loads(session_path.read_text(encoding="utf-8"))
    episode_id = str(payload.get("last_episode_id", "") or "")
    if not episode_id:
        raise RuntimeError("no episode_id recorded; pass --episode-id explicitly")
    return episode_id


def openenv_step(*, output_dir: str, action_text: str, episode_id: str = "") -> dict[str, Any]:
    response = _openenv_call(
        output_dir,
        {
            "action": "step",
            "episode_id": episode_id or _last_episode_id(output_dir),
            "action_text": action_text,
        },
    )
    return _write_openenv_response(output_dir, response)


def openenv_state(*, output_dir: str, episode_id: str = "") -> dict[str, Any]:
    response = _openenv_call(
        output_dir,
        {
            "action": "state",
            "episode_id": episode_id or _last_episode_id(output_dir),
        },
    )
    return _write_openenv_response(output_dir, response)


def openenv_checkpoint(*, output_dir: str, episode_id: str = "", label: str = "") -> dict[str, Any]:
    response = _openenv_call(
        output_dir,
        {
            "action": "checkpoint",
            "episode_id": episode_id or _last_episode_id(output_dir),
            "label": label,
        },
    )
    return _write_openenv_response(output_dir, response)


def openenv_restore(*, output_dir: str, checkpoint_id: str, episode_id: str = "") -> dict[str, Any]:
    response = _openenv_call(
        output_dir,
        {
            "action": "restore",
            "episode_id": episode_id or _last_episode_id(output_dir),
            "checkpoint_id": checkpoint_id,
        },
    )
    return _write_openenv_response(output_dir, response)


def openenv_stop(*, output_dir: str, episode_id: str = "", shutdown_server: bool = True) -> dict[str, Any]:
    response = _openenv_call(
        output_dir,
        {
            "action": "stop",
            "episode_id": episode_id or _last_episode_id(output_dir),
        },
    )
    if shutdown_server:
        try:
            _openenv_call(output_dir, {"action": "shutdown"})
        finally:
            meta_path = _server_meta_path(output_dir)
            if meta_path.exists():
                meta_path.unlink()
    return _write_openenv_response(output_dir, response)
