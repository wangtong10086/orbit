"""Stateful OpenEnv bridge for upstream affinetes SWE-INFINITE."""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import signal
import subprocess
import sys
import time
from multiprocessing.connection import Listener
from pathlib import Path
from typing import Any


def _normalize(value: Any):
    if dataclasses.is_dataclass(value):
        return {key: _normalize(val) for key, val in dataclasses.asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _normalize(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if hasattr(value, "model_dump"):
        return _normalize(value.model_dump(mode="json"))
    return value


def _load_actor(repo_root: Path):
    env_dir = repo_root / "environments" / "SWE-INFINITE"
    sys.path.insert(0, str(env_dir))
    sys.path.insert(0, str(repo_root))
    from env import Actor  # type: ignore

    return Actor


def _patch_actor_for_stateful_openenv_server(Actor):
    allow_cleanup = os.getenv("ORBIT_OPENENV_ALLOW_STARTUP_STALE_CLEANUP", "").strip().lower()
    if allow_cleanup in {"1", "true", "yes"}:
        return Actor
    original = getattr(Actor, "_cleanup_stale_containers", None)
    if not callable(original):
        return Actor

    def _skip_cleanup(self):
        print("[ORBIT] Skipping upstream stale-container cleanup for stateful OpenEnv server startup")
        return None

    setattr(Actor, "_cleanup_stale_containers", _skip_cleanup)
    return Actor


def _docker_pull_timeout_secs() -> int:
    try:
        return max(1, int(os.getenv("ORBIT_OPENENV_DOCKER_PULL_TIMEOUT_SECS", "1800")))
    except Exception:
        return 1800


def _docker_pull_retries() -> int:
    try:
        return max(1, int(os.getenv("ORBIT_OPENENV_DOCKER_PULL_RETRIES", "3")))
    except Exception:
        return 3


def _docker_pull_retry_delay_secs() -> float:
    try:
        return max(0.0, float(os.getenv("ORBIT_OPENENV_DOCKER_PULL_RETRY_DELAY_SECS", "5")))
    except Exception:
        return 5.0


def _patch_actor_for_local_image_reuse(Actor):
    original = getattr(Actor, "_start_container", None)
    if not callable(original):
        return Actor

    def _start_container(self, docker_image: str, container_name: str) -> str:
        inspect = subprocess.run(
            ["docker", "image", "inspect", docker_image],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if inspect.returncode != 0:
            timeout_secs = _docker_pull_timeout_secs()
            retries = _docker_pull_retries()
            delay_secs = _docker_pull_retry_delay_secs()
            last_error = ""
            print(f"[ORBIT] Local image missing, pre-pulling {docker_image} with timeout={timeout_secs}s retries={retries}")
            for attempt in range(1, retries + 1):
                pull = subprocess.run(
                    ["docker", "pull", docker_image],
                    capture_output=True,
                    text=True,
                    timeout=timeout_secs,
                )
                if pull.returncode == 0:
                    break
                last_error = (pull.stderr or pull.stdout or "").strip()
                if attempt >= retries:
                    raise RuntimeError(f"docker pull failed for {docker_image}: {last_error}")
                time.sleep(delay_secs)
        else:
            print(f"[ORBIT] Reusing local image {docker_image}; skipping docker pull")

        cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            "-w", "/app",
            "--rm", "--init",
            "--stop-timeout", "10",
            "--memory", "4g",
            "--memory-swap", "6g",
            "--network=host",
            "--entrypoint", "",
            docker_image,
            "sleep", "7200",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to start container: {result.stderr}")
        container_id = result.stdout.strip()
        print(f"[SWE-INFINITE] Started container {container_name} ({container_id[:12]})")
        return container_id

    setattr(Actor, "_start_container", _start_container)
    return Actor


def _write_ready(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run a stateful OpenEnv bridge for affinetes SWE-INFINITE")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--socket-path", required=True)
    parser.add_argument("--ready-file", required=True)
    parser.add_argument("--cache-dir", default="/tmp/swe-infinite-cache")
    parser.add_argument("--api-key", default="")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    socket_path = Path(args.socket_path)
    ready_file = Path(args.ready_file)
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists():
        socket_path.unlink()

    Actor = _patch_actor_for_local_image_reuse(
        _patch_actor_for_stateful_openenv_server(_load_actor(repo_root))
    )
    actor = Actor(api_key=args.api_key or None, cache_dir=args.cache_dir)
    listener = Listener(str(socket_path), family="AF_UNIX")

    def _cleanup(*_unused):
        try:
            listener.close()
        finally:
            if socket_path.exists():
                socket_path.unlink()
            raise SystemExit(0)

    signal.signal(signal.SIGTERM, _cleanup)
    signal.signal(signal.SIGINT, _cleanup)

    _write_ready(
        ready_file,
        {
            "pid": os.getpid(),
            "socket_path": str(socket_path),
            "repo_root": str(repo_root),
        },
    )

    while True:
        conn = listener.accept()
        try:
            request = conn.recv()
            action = str(request.get("action") or "")
            if action == "reset":
                response = asyncio.run(
                    actor.reset(
                        task_id=request["task_id"],
                        seed=request.get("seed"),
                        step_limit=int(request.get("step_limit") or 100),
                        command_timeout=int(request.get("command_timeout") or 300),
                    )
                )
                conn.send(_normalize(response))
            elif action == "state":
                if hasattr(actor, "state"):
                    response = asyncio.run(actor.state(episode_id=request.get("episode_id") or None))
                else:
                    response = {
                        "observation": "state is not supported by this environment",
                        "episode_id": request.get("episode_id") or None,
                        "done": True,
                        "truncated": True,
                        "checkpoint_capable": False,
                        "latest_checkpoint_id": "",
                        "info": {
                            "error": {
                                "type": "unsupported_operation",
                                "message": "state is not supported by this environment",
                                "retryable": False,
                            }
                        },
                    }
                conn.send(_normalize(response))
            elif action == "checkpoint":
                if hasattr(actor, "checkpoint"):
                    response = asyncio.run(
                        actor.checkpoint(
                            episode_id=request.get("episode_id") or None,
                            label=request.get("label") or "",
                        )
                    )
                else:
                    response = {
                        "episode_id": request.get("episode_id") or None,
                        "checkpoint_id": "",
                        "info": {
                            "error": {
                                "type": "unsupported_operation",
                                "message": "checkpoint is not supported by this environment",
                                "retryable": False,
                            }
                        },
                    }
                conn.send(_normalize(response))
            elif action == "restore":
                if hasattr(actor, "restore"):
                    response = asyncio.run(
                        actor.restore(
                            episode_id=request.get("episode_id") or None,
                            checkpoint_id=request.get("checkpoint_id") or "",
                        )
                    )
                else:
                    response = {
                        "observation": "restore is not supported by this environment",
                        "episode_id": request.get("episode_id") or None,
                        "checkpoint_id": request.get("checkpoint_id") or "",
                        "done": True,
                        "truncated": True,
                        "info": {
                            "error": {
                                "type": "unsupported_operation",
                                "message": "restore is not supported by this environment",
                                "retryable": False,
                            }
                        },
                    }
                conn.send(_normalize(response))
            elif action == "step":
                response = asyncio.run(
                    actor.step(
                        action=request["action_text"],
                        episode_id=request.get("episode_id") or None,
                    )
                )
                conn.send(_normalize(response))
            elif action == "stop":
                response = asyncio.run(actor.stop(episode_id=request.get("episode_id") or None))
                conn.send(_normalize(response))
            elif action == "shutdown":
                conn.send({"status": "ok", "shutdown": True})
                conn.close()
                _cleanup()
            else:
                conn.send({"status": "error", "message": f"unsupported action: {action}"})
        finally:
            try:
                conn.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
