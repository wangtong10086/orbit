"""Bounded, observable batch launcher for SWE synth/eval runs."""

from __future__ import annotations

import argparse
from collections import deque
import concurrent.futures
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .runner import _load_task_payload, _pull_task_image, _resolve_task_image

READY_MARKER = "The server is fired up and ready to roll!"
INFRA_TERMINAL_STATUSES = {
    "runtime_bootstrap_failed",
    "student_transport_failed",
    "openenv_failed",
    "launch_aborted",
}
MODEL_TERMINAL_STATUSES = {
    "model_stop",
    "context_limit",
    "max_steps",
    "failed_loop_budget",
    "teacher_stop",
}
COMPLETED_TERMINAL_STATUSES = {"done", "truncated"}
_RUNNING_REQ_RE = re.compile(r"#running-req:\s*(\d+)")
_GEN_THROUGHPUT_RE = re.compile(r"gen throughput(?: \(token/s\))?:\s*([0-9.]+)")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _iso_utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _selected_tasks(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    tasks = payload.get("selected_tasks")
    if not isinstance(tasks, list) or not tasks:
        raise RuntimeError(f"selected_tasks manifest is empty or invalid: {path}")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for item in tasks:
        if not isinstance(item, dict):
            raise RuntimeError(f"selected_tasks entry is not an object: {item!r}")
        task_id = str(item.get("task_id") or "").strip()
        if not task_id:
            raise RuntimeError(f"selected_tasks entry missing task_id: {item!r}")
        if task_id in seen:
            raise RuntimeError(f"duplicate task_id in selected_tasks.json: {task_id}")
        seen.add(task_id)
        normalized.append(dict(item))
    return normalized


def _validate_prewarm_manifest(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    images = payload.get("images")
    if not isinstance(images, list) or not images:
        raise RuntimeError(f"image prewarm manifest is empty or invalid: {path}")
    bad = [item for item in images if str(item.get("status") or "") not in {"cached", "pulled"}]
    if bad:
        failed = ", ".join(str(item.get("image") or "") for item in bad[:5])
        raise RuntimeError(f"image prewarm manifest contains non-ready images: {failed}")
    return payload


def _base_url(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/v1"):
        return base[:-3]
    return base


def _http_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    body = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _ssh_read_text(*, host: str, port: int, user: str, remote_path: str, tail_lines: int = 400) -> str:
    proc = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=no",
            "-p",
            str(port),
            f"{user}@{host}",
            f"tail -n {tail_lines} {remote_path}",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout


def _ssh_log_contains(*, host: str, port: int, user: str, remote_path: str, needle: str) -> bool:
    proc = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=no",
            "-p",
            str(port),
            f"{user}@{host}",
            f"grep -Fq {json.dumps(needle)} {remote_path}",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode == 0


def _parse_sglang_metrics(text: str) -> dict[str, Any]:
    running_req = None
    gen_throughput = None
    for line in text.splitlines():
        req_match = _RUNNING_REQ_RE.search(line)
        if req_match:
            running_req = int(req_match.group(1))
        throughput_match = _GEN_THROUGHPUT_RE.search(line)
        if throughput_match:
            gen_throughput = float(throughput_match.group(1))
    return {"running_req": running_req, "gen_throughput": gen_throughput}


def ready_gate(
    *,
    api_base: str,
    model: str,
    timeout_secs: int,
    student_log_path: str,
    student_ssh_host: str,
    student_ssh_port: int,
    student_ssh_user: str = "root",
) -> dict[str, Any]:
    deadline = time.time() + timeout_secs
    base_url = _base_url(api_base)
    last_error = "student ready gate did not run"
    while time.time() < deadline:
        try:
            models = _http_json("GET", f"{api_base.rstrip('/')}/models", timeout=15)
            model_ids = {
                str(item.get("id") or "")
                for item in (models.get("data") if isinstance(models, dict) else [])
                if isinstance(item, dict)
            }
            if model not in model_ids:
                last_error = f"model {model} not present in /v1/models"
                time.sleep(2)
                continue
            _http_json("GET", f"{base_url}/model_info", timeout=15)
            smoke = _http_json(
                "POST",
                f"{api_base.rstrip('/')}/chat/completions",
                payload={
                    "model": model,
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                    "temperature": 0.0,
                    "max_tokens": 8,
                },
                timeout=30,
            )
            smoke_text = ""
            try:
                message = smoke["choices"][0]["message"]
                smoke_text = str(message.get("content") or message.get("reasoning_content") or "")
            except Exception:
                smoke_text = ""
            if not smoke_text.strip():
                last_error = "smoke chat.completions returned empty content"
                time.sleep(2)
                continue
            log_ready = False
            if student_log_path and student_ssh_host:
                log_ready = _ssh_log_contains(
                    host=student_ssh_host,
                    port=student_ssh_port,
                    user=student_ssh_user,
                    remote_path=student_log_path,
                    needle=READY_MARKER,
                )
                if not log_ready:
                    last_error = "student log is missing ready marker"
                    time.sleep(2)
                    continue
            return {
                "api_base": api_base,
                "model": model,
                "model_ids": sorted(model_ids),
                "smoke_text": smoke_text.strip(),
                "log_ready": log_ready,
                "checked_at": _iso_utc_now(),
            }
        except Exception as exc:
            last_error = str(exc)
            time.sleep(2)
    raise RuntimeError(f"student ready gate failed: {last_error}")


def classify_manifest_terminal_state(payload: dict[str, Any]) -> str:
    terminal_status = str(payload.get("terminal_status") or "")
    if terminal_status in INFRA_TERMINAL_STATUSES:
        return "failed_infra"
    if terminal_status in MODEL_TERMINAL_STATUSES:
        return "failed_model"
    if terminal_status in COMPLETED_TERMINAL_STATUSES:
        return "completed"
    return "failed_model"


def cleanup_orphan_openenv_server(output_dir: Path) -> bool:
    meta_path = output_dir / ".runtime" / "openenv_server.json"
    if not meta_path.exists():
        return False
    try:
        meta = _read_json(meta_path)
    except Exception:
        meta_path.unlink(missing_ok=True)
        return False
    pid = int(meta.get("pid") or 0)
    killed = False
    if pid > 0:
        try:
            os.kill(pid, signal.SIGTERM)
            killed = True
        except OSError:
            pass
    socket_path = str(meta.get("socket_path") or "")
    if socket_path:
        Path(socket_path).unlink(missing_ok=True)
    meta_path.unlink(missing_ok=True)
    return killed


def write_launch_aborted_manifest(*, task_id: str, output_dir: Path, attempt: int, reason: str, transport_retries_used: int = 0) -> Path:
    manifest_path = output_dir / "manifests" / "synthesis_run.json"
    payload = {
        "schema_version": "affinetes_openenv_synthesis.v1",
        "task_id": task_id,
        "clean_eval": True,
        "eval_mode": True,
        "teacher_calls": 0,
        "teacher_branch_calls": 0,
        "teacher_think_calls": 0,
        "restore_budget_used": 0,
        "restore_target_applied": "CURRENT",
        "checkpoint_ring_depth": 0,
        "transport_retries_used": transport_retries_used,
        "terminal_status": "launch_aborted",
        "failure_stage": "launcher",
        "failure_reason": "process_exited_without_manifest",
        "exception_type": "LaunchAborted",
        "exception_message": reason,
        "attempt": attempt,
        "verified_success": False,
        "final_reward": 0.0,
        "final_test_stats": {},
        "events_path": str(output_dir / "raw" / "synthesis_events.jsonl"),
    }
    _write_json(manifest_path, payload)
    return manifest_path


@dataclass
class TaskRun:
    task_id: str
    image: str = ""
    attempt: int = 0
    status: str = "pending"
    proc: subprocess.Popen[str] | None = None
    output_dir: Path | None = None
    manifest: dict[str, Any] | None = None
    transport_retries_used: int = 0
    infra_retries_used: int = 0
    started: bool = False
    pid: int = 0
    last_error: str = ""
    launch_log: Path | None = None
    bootstrap_ready_file: Path | None = None
    rollout_release_file: Path | None = None
    rollout_released: bool = False
    launch_started_at: str = ""
    bootstrap_ready_at: str = ""
    first_model_action_at: str = ""
    terminal_at: str = ""
    state_history: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "image": self.image,
            "attempt": self.attempt,
            "status": self.status,
            "pid": self.pid,
            "output_dir": str(self.output_dir) if self.output_dir else "",
            "launch_log": str(self.launch_log) if self.launch_log else "",
            "transport_retries_used": self.transport_retries_used,
            "infra_retries_used": self.infra_retries_used,
            "started": self.started,
            "last_error": self.last_error,
            "rollout_released": self.rollout_released,
            "launch_started_at": self.launch_started_at,
            "bootstrap_ready_at": self.bootstrap_ready_at,
            "first_model_action_at": self.first_model_action_at,
            "terminal_at": self.terminal_at,
            "terminal_status": str((self.manifest or {}).get("terminal_status") or ""),
            "verified_success": bool((self.manifest or {}).get("verified_success")),
        }


@dataclass
class ImagePullState:
    image: str
    status: str = "pending"
    future: concurrent.futures.Future[dict[str, Any]] | None = None
    attempts: int = 0
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "image": self.image,
            "status": self.status,
            "attempts": self.attempts,
            "error": self.error,
        }


def _has_model_action(events_path: Path) -> bool:
    if not events_path.exists() or events_path.stat().st_size == 0:
        return False
    with events_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if '"kind": "model_action"' in line:
                return True
    return False


def _tail_text(path: Path, lines: int = 60) -> str:
    if not path.exists():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])


def _warm_ready_paths(output_dir: Path) -> tuple[Path, Path]:
    runtime_dir = output_dir / ".runtime"
    return runtime_dir / "bootstrap_ready.json", runtime_dir / "rollout_release.json"


def _inflight_task_count(runs: dict[str, TaskRun]) -> int:
    return sum(1 for run in runs.values() if run.status in {"bootstrapping", "warm_ready", "running"})


def _rollout_slot_usage(runs: dict[str, TaskRun]) -> int:
    return sum(1 for run in runs.values() if run.status == "running" or (run.status == "warm_ready" and run.rollout_released))


def _warm_ready_count(runs: dict[str, TaskRun]) -> int:
    return sum(1 for run in runs.values() if run.status == "warm_ready")


def _release_warm_ready_runs(runs: dict[str, TaskRun], *, max_live_rollouts: int) -> int:
    released = 0
    rollout_slots_used = _rollout_slot_usage(runs)
    for run in sorted((item for item in runs.values() if item.status == "warm_ready" and not item.rollout_released), key=lambda item: (item.attempt, item.task_id)):
        if rollout_slots_used >= max_live_rollouts:
            break
        if run.rollout_release_file is None:
            continue
        run.rollout_release_file.parent.mkdir(parents=True, exist_ok=True)
        run.rollout_release_file.write_text(_iso_utc_now() + "\n", encoding="utf-8")
        run.rollout_released = True
        rollout_slots_used += 1
        released += 1
    return released


def _task_image_for(cache_dir: str, task_id: str) -> str:
    payload = _load_task_payload(cache_dir, task_id)
    return _resolve_task_image(payload)


def _ready_pending_count(runs: dict[str, TaskRun], image_states: dict[str, ImagePullState]) -> int:
    return sum(1 for run in runs.values() if run.status == "pending" and image_states.get(run.image, ImagePullState(run.image, status="ready")).status == "ready")


def _prefetched_pending_count(runs: dict[str, TaskRun], image_states: dict[str, ImagePullState]) -> int:
    return sum(
        1
        for run in runs.values()
        if run.status == "pending"
        and image_states.get(run.image, ImagePullState(run.image, status="ready")).status in {"ready", "pulling"}
    )


def _image_pulls_inflight(image_states: dict[str, ImagePullState]) -> int:
    return sum(1 for state in image_states.values() if state.status == "pulling")


def _refresh_image_pull_queue(
    image_pull_queue: deque[str],
    queued_images: set[str],
    *,
    ordered_task_ids: list[str],
    runs: dict[str, TaskRun],
    image_states: dict[str, ImagePullState],
    prefetch_target: int,
) -> None:
    frontier: list[str] = []
    for task_id in ordered_task_ids:
        run = runs[task_id]
        if run.status in {"completed", "failed_infra", "failed_model", "bootstrapping", "warm_ready", "running"}:
            continue
        frontier.append(task_id)
        if len(frontier) >= prefetch_target:
            break
    seen: set[str] = set()
    for task_id in frontier:
        image = runs[task_id].image
        if image in seen:
            continue
        seen.add(image)
        state = image_states[image]
        if state.status != "pending" or image in queued_images:
            continue
        image_pull_queue.append(image)
        queued_images.add(image)


def _refresh_bootstrap_queue(
    bootstrap_queue: deque[str],
    queued_tasks: set[str],
    *,
    ordered_task_ids: list[str],
    runs: dict[str, TaskRun],
    image_states: dict[str, ImagePullState],
) -> None:
    for task_id in ordered_task_ids:
        run = runs[task_id]
        if run.status != "pending":
            continue
        if image_states[run.image].status != "ready":
            continue
        if task_id in queued_tasks:
            continue
        bootstrap_queue.append(task_id)
        queued_tasks.add(task_id)


def _build_synthesize_command(
    *,
    task_id: str,
    output_dir: Path,
    upstream_repo_path: str,
    upstream_ref: str,
    cache_dir: str,
    model: str,
    api_base: str,
    api_key: str,
    step_limit: int,
    max_steps: int,
    model_timeout: int,
    student_max_context_tokens: int,
    eval_max_context_tokens: int,
    student_max_new_tokens: int,
    transport_only_retries: int,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "orbit",
        "data",
        "swe-collect",
        "synthesize",
        "--upstream-repo-path",
        upstream_repo_path,
        "--upstream-ref",
        upstream_ref,
        "--cache-dir",
        cache_dir,
        "--task-id",
        task_id,
        "--model",
        model,
        "--api-base",
        api_base,
        "--api-key",
        api_key,
        "--step-limit",
        str(step_limit),
        "--max-steps",
        str(max_steps),
        "--model-timeout",
        str(model_timeout),
        "--student-enable-thinking",
        "--student-max-context-tokens",
        str(student_max_context_tokens),
        "--student-max-new-tokens",
        str(student_max_new_tokens),
        "--eval-mode",
        "--eval-max-context-tokens",
        str(eval_max_context_tokens),
        "--transport-only-retries",
        str(transport_only_retries),
        "--output-dir",
        str(output_dir),
    ]


def _sample_remote_metrics(*, student_ssh_host: str, student_ssh_port: int, student_ssh_user: str, student_log_path: str) -> dict[str, Any]:
    if not (student_ssh_host and student_log_path):
        return {"running_req": None, "gen_throughput": None}
    tail = _ssh_read_text(
        host=student_ssh_host,
        port=student_ssh_port,
        user=student_ssh_user,
        remote_path=student_log_path,
        tail_lines=400,
    )
    return _parse_sglang_metrics(tail)


def launch_clean_eval_batch(
    *,
    selected_tasks_json: str,
    image_prewarm_json: str = "",
    output_dir: str,
    upstream_repo_path: str,
    upstream_ref: str,
    cache_dir: str,
    model: str,
    api_base: str,
    api_key: str,
    student_log_path: str,
    student_ssh_host: str,
    student_ssh_port: int,
    student_ssh_user: str = "root",
    bootstrap_concurrency: int = 8,
    max_live_rollouts: int = 32,
    warm_ready_buffer: int = 16,
    poll_interval_secs: int = 2,
    metrics_interval_secs: int = 30,
    ready_timeout_secs: int = 900,
    task_limit: int = 0,
    step_limit: int = 200,
    max_steps: int = 200,
    model_timeout: int = 300,
    student_max_context_tokens: int = 65536,
    eval_max_context_tokens: int = 65536,
    student_max_new_tokens: int = 4096,
    transport_only_retries: int = 1,
    max_infra_restarts: int = 1,
    max_transport_restarts: int = 1,
    stream_images: bool = False,
    image_pull_concurrency: int = 4,
    image_pull_timeout_secs: int = 1800,
    image_pull_retries: int = 3,
    image_inspect_timeout_secs: int = 120,
    image_inspect_retries: int = 2,
    ready_task_buffer: int = 32,
    image_prefetch_task_buffer: int = 128,
    image_pull_dispatch_burst: int = 4,
    bootstrap_dispatch_burst: int = 4,
) -> dict[str, Any]:
    selected_path = Path(selected_tasks_json).resolve()
    prewarm_path = Path(image_prewarm_json).resolve() if image_prewarm_json else None
    root = Path(output_dir).resolve()
    if root.exists() and any(root.iterdir()):
        raise RuntimeError(f"output_dir must be empty or absent: {root}")
    root.mkdir(parents=True, exist_ok=True)

    tasks = _selected_tasks(selected_path)
    if task_limit > 0:
        tasks = tasks[:task_limit]
    if not stream_images:
        if prewarm_path is None:
            raise RuntimeError("image_prewarm_json is required unless --stream-images is enabled")
        _validate_prewarm_manifest(prewarm_path)

    ready_payload = ready_gate(
        api_base=api_base,
        model=model,
        timeout_secs=ready_timeout_secs,
        student_log_path=student_log_path,
        student_ssh_host=student_ssh_host,
        student_ssh_port=student_ssh_port,
        student_ssh_user=student_ssh_user,
    )
    _write_json(root / 'ready_gate.json', ready_payload)
    if prewarm_path is not None and prewarm_path.exists():
        shutil.copy2(prewarm_path, root / 'image_prewarm.json')
    shutil.copy2(selected_path, root / 'selected_tasks.json')

    state_path = root / 'campaign_state.json'
    metrics_path = root / 'campaign_metrics.jsonl'
    ordered_task_ids = [str(item['task_id']) for item in tasks]
    runs: dict[str, TaskRun] = {}
    image_states: dict[str, ImagePullState] = {}
    for task_id in ordered_task_ids:
        image = _task_image_for(cache_dir, task_id)
        runs[task_id] = TaskRun(task_id=task_id, image=image)
        image_states.setdefault(image, ImagePullState(image=image, status='ready' if not stream_images else 'pending'))

    pull_pool = concurrent.futures.ThreadPoolExecutor(max_workers=max(1, int(image_pull_concurrency))) if stream_images else None
    image_pull_futures: dict[concurrent.futures.Future[dict[str, Any]], str] = {}
    image_pull_queue: deque[str] = deque()
    queued_images: set[str] = set()
    bootstrap_queue: deque[str] = deque()
    queued_tasks: set[str] = set()

    def _launch(run: TaskRun) -> None:
        run.attempt += 1
        run.output_dir = root / f'task-{run.task_id}-attempt-{run.attempt}'
        run.output_dir.mkdir(parents=True, exist_ok=True)
        run.launch_log = run.output_dir / 'launch.log'
        ready_file, release_file = _warm_ready_paths(run.output_dir)
        run.bootstrap_ready_file = ready_file
        run.rollout_release_file = release_file
        run.rollout_released = False
        run.launch_started_at = _iso_utc_now()
        run.bootstrap_ready_at = ''
        run.first_model_action_at = ''
        run.terminal_at = ''
        command = _build_synthesize_command(
            task_id=run.task_id,
            output_dir=run.output_dir,
            upstream_repo_path=upstream_repo_path,
            upstream_ref=upstream_ref,
            cache_dir=cache_dir,
            model=model,
            api_base=api_base,
            api_key=api_key,
            step_limit=step_limit,
            max_steps=max_steps,
            model_timeout=model_timeout,
            student_max_context_tokens=student_max_context_tokens,
            eval_max_context_tokens=eval_max_context_tokens,
            student_max_new_tokens=student_max_new_tokens,
            transport_only_retries=transport_only_retries,
        )
        env = os.environ.copy()
        env['ORBIT_SWE_PAUSE_BEFORE_FIRST_MODEL_ACTION'] = 'true'
        env['ORBIT_SWE_BOOTSTRAP_READY_FILE'] = str(ready_file)
        env['ORBIT_SWE_ROLLOUT_RELEASE_FILE'] = str(release_file)
        with run.launch_log.open('a', encoding='utf-8') as handle:
            proc = subprocess.Popen(
                command,
                cwd=str(Path(__file__).resolve().parents[3]),
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
                env=env,
            )
        run.proc = proc
        run.pid = proc.pid
        run.status = 'bootstrapping'
        run.manifest = None
        run.last_error = ''
        run.state_history.append(run.status)

    def _record_state() -> None:
        payload = {
            'schema_version': 'affinetes_swe_batch_launcher.v1',
            'selected_tasks_json': str(selected_path),
            'image_prewarm_json': str(prewarm_path) if prewarm_path else '',
            'output_dir': str(root),
            'bootstrap_concurrency': bootstrap_concurrency,
            'max_live_rollouts': max_live_rollouts,
            'warm_ready_buffer': warm_ready_buffer,
            'stream_images': stream_images,
            'image_pull_concurrency': image_pull_concurrency,
            'image_pull_timeout_secs': image_pull_timeout_secs,
            'image_pull_retries': image_pull_retries,
            'image_inspect_timeout_secs': image_inspect_timeout_secs,
            'image_inspect_retries': image_inspect_retries,
            'ready_task_buffer': ready_task_buffer,
            'image_prefetch_task_buffer': image_prefetch_task_buffer,
            'image_pull_dispatch_burst': image_pull_dispatch_burst,
            'bootstrap_dispatch_burst': bootstrap_dispatch_burst,
            'queued_image_pulls': list(image_pull_queue),
            'queued_bootstraps': list(bootstrap_queue),
            'image_states': [state.as_dict() for state in sorted(image_states.values(), key=lambda item: item.image)],
            'tasks': [run.as_dict() for run in runs.values()],
        }
        _write_json(state_path, payload)

    def _process_image_pull_results() -> None:
        if not stream_images:
            return
        done = [future for future in image_pull_futures if future.done()]
        for future in done:
            image = image_pull_futures.pop(future)
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    'image': image,
                    'status': 'retryable_failed',
                    'attempts': 1,
                    'error': f'{type(exc).__name__}: {exc}',
                }
            state = image_states[image]
            state.attempts += int(result.get('attempts') or 0)
            state.error = str(result.get('error') or '')
            result_status = str(result.get('status') or '')
            if result_status in {'cached', 'pulled'}:
                state.status = 'ready'
            elif result_status == 'retryable_failed':
                state.status = 'pending'
            else:
                state.status = 'failed'
            state.future = None
            if state.status == 'failed':
                reason = state.error or f'image prewarm failed for {image}'
                for task_id in ordered_task_ids:
                    run = runs[task_id]
                    if run.image != image or run.status in {'completed', 'failed_infra', 'failed_model', 'bootstrapping', 'warm_ready', 'running'}:
                        continue
                    if run.output_dir is None:
                        run.output_dir = root / f'task-{run.task_id}-attempt-0'
                        run.output_dir.mkdir(parents=True, exist_ok=True)
                    write_launch_aborted_manifest(
                        task_id=run.task_id,
                        output_dir=run.output_dir,
                        attempt=run.attempt,
                        reason=reason,
                        transport_retries_used=run.transport_retries_used,
                    )
                    run.manifest = _read_json(run.output_dir / 'manifests' / 'synthesis_run.json')
                    run.status = 'failed_infra'
                    run.terminal_at = run.terminal_at or _iso_utc_now()
                    run.state_history.append(run.status)

    def _schedule_image_pulls() -> None:
        if not stream_images or pull_pool is None:
            return
        _process_image_pull_results()
        ready_pending = _ready_pending_count(runs, image_states)
        prefetched_pending = _prefetched_pending_count(runs, image_states)
        ready_target = max(1, int(ready_task_buffer))
        prefetch_target = max(ready_target, int(image_prefetch_task_buffer))
        if ready_pending < ready_target or prefetched_pending < prefetch_target:
            _refresh_image_pull_queue(
                image_pull_queue,
                queued_images,
                ordered_task_ids=ordered_task_ids,
                runs=runs,
                image_states=image_states,
                prefetch_target=prefetch_target,
            )
        inflight = len(image_pull_futures)
        dispatched = 0
        while image_pull_queue and inflight < max(1, int(image_pull_concurrency)) and dispatched < max(1, int(image_pull_dispatch_burst)):
            image = image_pull_queue.popleft()
            queued_images.discard(image)
            state = image_states[image]
            if state.status != 'pending':
                continue
            state.status = 'pulling'
            state.future = pull_pool.submit(
                _pull_task_image,
                image=image,
                timeout_secs=int(image_pull_timeout_secs),
                retries=max(1, int(image_pull_retries)),
                inspect_timeout_secs=int(image_inspect_timeout_secs),
                inspect_retries=max(1, int(image_inspect_retries)),
            )
            image_pull_futures[state.future] = image
            inflight += 1
            dispatched += 1

    last_metrics = 0.0
    last_started_for_rate = 0
    last_completed_for_rate = 0
    try:
        while True:
            _schedule_image_pulls()
            for run in runs.values():
                if run.status in {'completed', 'failed_infra', 'failed_model'}:
                    continue
                manifest_path = run.output_dir / 'manifests' / 'synthesis_run.json' if run.output_dir else None
                events_path = run.output_dir / 'raw' / 'synthesis_events.jsonl' if run.output_dir else None
                if manifest_path and manifest_path.exists():
                    run.manifest = _read_json(manifest_path)
                    run.status = classify_manifest_terminal_state(run.manifest)
                    run.terminal_at = run.terminal_at or _iso_utc_now()
                    run.state_history.append(run.status)
                    run.proc = None
                    run.pid = 0
                    continue
                if run.proc and run.proc.poll() is None:
                    if events_path and _has_model_action(events_path):
                        run.started = True
                        run.first_model_action_at = run.first_model_action_at or _iso_utc_now()
                        if run.status != 'running':
                            run.status = 'running'
                            run.state_history.append(run.status)
                    elif run.bootstrap_ready_file and run.bootstrap_ready_file.exists():
                        run.bootstrap_ready_at = run.bootstrap_ready_at or _iso_utc_now()
                        if run.status != 'warm_ready':
                            run.status = 'warm_ready'
                            run.state_history.append(run.status)
                    elif run.status != 'bootstrapping':
                        run.status = 'bootstrapping'
                        run.state_history.append(run.status)
                    continue
                if run.proc and run.proc.poll() is not None and run.status not in {'completed', 'failed_infra', 'failed_model'}:
                    cleaned = cleanup_orphan_openenv_server(run.output_dir) if run.output_dir else False
                    log_tail = _tail_text(run.launch_log) if run.launch_log else ''
                    lower_tail = log_tail.lower()
                    retryable_transport = 'request timed out' in lower_tail or 'connection error' in lower_tail
                    if retryable_transport and run.transport_retries_used < max_transport_restarts:
                        run.transport_retries_used += 1
                        run.status = 'pending'
                        run.proc = None
                        run.pid = 0
                        run.last_error = 'transport retry scheduled'
                        continue
                    if run.infra_retries_used < max_infra_restarts:
                        run.infra_retries_used += 1
                        run.status = 'pending'
                        run.proc = None
                        run.pid = 0
                        run.last_error = 'infra retry scheduled'
                        continue
                    if run.output_dir:
                        write_launch_aborted_manifest(
                            task_id=run.task_id,
                            output_dir=run.output_dir,
                            attempt=run.attempt,
                            reason=log_tail or 'process exited without manifest',
                            transport_retries_used=run.transport_retries_used,
                        )
                        run.manifest = _read_json(run.output_dir / 'manifests' / 'synthesis_run.json')
                    run.status = 'failed_infra'
                    run.terminal_at = run.terminal_at or _iso_utc_now()
                    run.state_history.append(run.status)
                    run.proc = None
                    run.pid = 0
                    run.last_error = 'orphan openenv cleaned' if cleaned else 'process exited without manifest'

            _release_warm_ready_runs(runs, max_live_rollouts=max_live_rollouts)
            _process_image_pull_results()
            active_total = _inflight_task_count(runs)
            active_bootstraps = sum(1 for run in runs.values() if run.status == 'bootstrapping')
            _refresh_bootstrap_queue(
                bootstrap_queue,
                queued_tasks,
                ordered_task_ids=ordered_task_ids,
                runs=runs,
                image_states=image_states,
            )
            max_inflight = max_live_rollouts + warm_ready_buffer
            launched = 0
            while (
                bootstrap_queue
                and active_total < max_inflight
                and active_bootstraps < bootstrap_concurrency
                and launched < max(1, int(bootstrap_dispatch_burst))
            ):
                task_id = bootstrap_queue.popleft()
                queued_tasks.discard(task_id)
                candidate = runs[task_id]
                if candidate.status != 'pending':
                    continue
                if stream_images and image_states[candidate.image].status != 'ready':
                    continue
                _launch(candidate)
                active_total += 1
                active_bootstraps += 1
                launched += 1

            _record_state()
            now = time.time()
            if now - last_metrics >= metrics_interval_secs:
                remote_metrics = _sample_remote_metrics(
                    student_ssh_host=student_ssh_host,
                    student_ssh_port=student_ssh_port,
                    student_ssh_user=student_ssh_user,
                    student_log_path=student_log_path,
                )
                started_count = sum(1 for run in runs.values() if run.started or run.status in {'completed', 'failed_infra', 'failed_model'})
                completed_count = sum(1 for run in runs.values() if run.status == 'completed')
                elapsed_minutes = max((now - last_metrics) / 60.0, 1e-9) if last_metrics else 1.0
                metrics = {
                    'ts': _iso_utc_now(),
                    'started': started_count,
                    'completed': completed_count,
                    'failed_infra': sum(1 for run in runs.values() if run.status == 'failed_infra'),
                    'failed_model': sum(1 for run in runs.values() if run.status == 'failed_model'),
                    'verified': sum(1 for run in runs.values() if bool((run.manifest or {}).get('verified_success'))),
                    'active_rollouts': sum(1 for run in runs.values() if run.status == 'running'),
                    'active_bootstraps': sum(1 for run in runs.values() if run.status == 'bootstrapping'),
                    'warm_ready': _warm_ready_count(runs),
                    'active_image_pulls': len(image_pull_futures),
                    'queued_image_pulls': len(image_pull_queue),
                    'queued_bootstraps': len(bootstrap_queue),
                    'ready_pending': _ready_pending_count(runs, image_states),
                    'prefetched_pending': _prefetched_pending_count(runs, image_states),
                    'started_per_min': round((started_count - last_started_for_rate) / elapsed_minutes, 3),
                    'completed_per_min': round((completed_count - last_completed_for_rate) / elapsed_minutes, 3),
                    'h200_running_req': remote_metrics.get('running_req'),
                    'h200_gen_throughput': remote_metrics.get('gen_throughput'),
                }
                with metrics_path.open('a', encoding='utf-8') as handle:
                    handle.write(json.dumps(metrics, ensure_ascii=False) + '\n')
                last_started_for_rate = started_count
                last_completed_for_rate = completed_count
                last_metrics = now

            if all(run.status in {'completed', 'failed_infra', 'failed_model'} for run in runs.values()):
                break
            time.sleep(poll_interval_secs)
    finally:
        if pull_pool is not None:
            pull_pool.shutdown(wait=False, cancel_futures=True)

    _record_state()
    return _read_json(state_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Launch a bounded SWE clean-eval batch with ready gates and metrics.')
    parser.add_argument('--selected-tasks-json', required=True)
    parser.add_argument('--image-prewarm-json', default='')
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--upstream-repo-path', required=True)
    parser.add_argument('--upstream-ref', required=True)
    parser.add_argument('--cache-dir', default='/tmp/swe-infinite-cache')
    parser.add_argument('--model', required=True)
    parser.add_argument('--api-base', required=True)
    parser.add_argument('--api-key', default='dummy')
    parser.add_argument('--student-log-path', default='')
    parser.add_argument('--student-ssh-host', default='')
    parser.add_argument('--student-ssh-port', type=int, default=22)
    parser.add_argument('--student-ssh-user', default='root')
    parser.add_argument('--bootstrap-concurrency', type=int, default=8)
    parser.add_argument('--max-live-rollouts', type=int, default=32)
    parser.add_argument('--warm-ready-buffer', type=int, default=16)
    parser.add_argument('--poll-interval-secs', type=int, default=2)
    parser.add_argument('--metrics-interval-secs', type=int, default=30)
    parser.add_argument('--ready-timeout-secs', type=int, default=900)
    parser.add_argument('--task-limit', type=int, default=0)
    parser.add_argument('--step-limit', type=int, default=200)
    parser.add_argument('--max-steps', type=int, default=200)
    parser.add_argument('--model-timeout', type=int, default=300)
    parser.add_argument('--student-max-context-tokens', type=int, default=65536)
    parser.add_argument('--eval-max-context-tokens', type=int, default=65536)
    parser.add_argument('--student-max-new-tokens', type=int, default=4096)
    parser.add_argument('--transport-only-retries', type=int, default=1)
    parser.add_argument('--max-infra-restarts', type=int, default=1)
    parser.add_argument('--max-transport-restarts', type=int, default=1)
    parser.add_argument('--stream-images', action='store_true')
    parser.add_argument('--image-pull-concurrency', type=int, default=4)
    parser.add_argument('--image-pull-timeout-secs', type=int, default=1800)
    parser.add_argument('--image-pull-retries', type=int, default=3)
    parser.add_argument('--image-inspect-timeout-secs', type=int, default=120)
    parser.add_argument('--image-inspect-retries', type=int, default=2)
    parser.add_argument('--ready-task-buffer', type=int, default=32)
    parser.add_argument('--image-prefetch-task-buffer', type=int, default=128)
    parser.add_argument('--image-pull-dispatch-burst', type=int, default=4)
    parser.add_argument('--bootstrap-dispatch-burst', type=int, default=4)
    args = parser.parse_args(argv)
    payload = launch_clean_eval_batch(
        selected_tasks_json=args.selected_tasks_json,
        image_prewarm_json=args.image_prewarm_json,
        output_dir=args.output_dir,
        upstream_repo_path=args.upstream_repo_path,
        upstream_ref=args.upstream_ref,
        cache_dir=args.cache_dir,
        model=args.model,
        api_base=args.api_base,
        api_key=args.api_key,
        student_log_path=args.student_log_path,
        student_ssh_host=args.student_ssh_host,
        student_ssh_port=args.student_ssh_port,
        student_ssh_user=args.student_ssh_user,
        bootstrap_concurrency=args.bootstrap_concurrency,
        max_live_rollouts=args.max_live_rollouts,
        warm_ready_buffer=args.warm_ready_buffer,
        poll_interval_secs=args.poll_interval_secs,
        metrics_interval_secs=args.metrics_interval_secs,
        ready_timeout_secs=args.ready_timeout_secs,
        task_limit=args.task_limit,
        step_limit=args.step_limit,
        max_steps=args.max_steps,
        model_timeout=args.model_timeout,
        student_max_context_tokens=args.student_max_context_tokens,
        eval_max_context_tokens=args.eval_max_context_tokens,
        student_max_new_tokens=args.student_max_new_tokens,
        transport_only_retries=args.transport_only_retries,
        max_infra_restarts=args.max_infra_restarts,
        max_transport_restarts=args.max_transport_restarts,
        stream_images=args.stream_images,
        image_pull_concurrency=args.image_pull_concurrency,
        image_pull_timeout_secs=args.image_pull_timeout_secs,
        image_pull_retries=args.image_pull_retries,
        image_inspect_timeout_secs=args.image_inspect_timeout_secs,
        image_inspect_retries=args.image_inspect_retries,
        ready_task_buffer=args.ready_task_buffer,
        image_prefetch_task_buffer=args.image_prefetch_task_buffer,
        image_pull_dispatch_burst=args.image_pull_dispatch_burst,
        bootstrap_dispatch_burst=args.bootstrap_dispatch_burst,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
