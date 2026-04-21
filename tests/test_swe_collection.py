"""Tests for black-box upstream affinetes SWE-INFINITE integration."""

from __future__ import annotations

from collections import deque
import json
import signal
import subprocess
import threading
import time
from pathlib import Path

from click.testing import CliRunner
import pytest

from orbit.cli import cli
from orbit.data.collect_adapters import collect_swe
from orbit.integrations.affinetes_swe import (
    openenv_checkpoint,
    openenv_reset,
    openenv_restore,
    run_openenv_synthesis,
    openenv_state,
    openenv_step,
    openenv_stop,
    parse_task_range,
    run_affinetes_swe_evaluate,
)
from orbit.integrations.affinetes_swe import synthesis as synthesis_module
from orbit.integrations.affinetes_swe import openenv_server as openenv_server_module
from orbit.integrations.affinetes_swe import runner as runner_module
from orbit.integrations.affinetes_swe import batch_launcher as batch_launcher_module
from orbit.integrations.affinetes_swe.runner import prepare_upstream_runtime
from orbit.integrations.affinetes_swe.runner import _server_socket_path
from orbit.tasks.collection.specs import SweCollectConfig


def _run(cmd: list[str], *, cwd: Path) -> str:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=True)
    return proc.stdout.strip()


@pytest.fixture(autouse=True)
def _isolated_shared_runtime_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(runner_module, "DEFAULT_SHARED_RUNTIME_CACHE_ROOT", str(tmp_path / "shared-runtime-cache"))


def _init_fake_affinetes_repo(tmp_path: Path, *, support_checkpoint: bool = True) -> tuple[Path, str]:
    repo = tmp_path / "affinetes"
    env_dir = repo / "environments" / "SWE-INFINITE"
    env_dir.mkdir(parents=True)
    (repo / "affinetes" / "core").mkdir(parents=True)
    (repo / "affinetes" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "affinetes" / "core" / "__init__.py").write_text("", encoding="utf-8")
    core_text = (
        "class OpenEnvResponse:\n"
        "    def __init__(self, **kwargs):\n"
        "        self.__dict__.update(kwargs)\n"
    )
    core_text += (
        "\nclass OpenEnvStateResponse:\n"
        "    def __init__(self, **kwargs):\n"
        "        self.__dict__.update(kwargs)\n"
        "\nclass OpenEnvCheckpointResponse:\n"
        "    def __init__(self, **kwargs):\n"
        "        self.__dict__.update(kwargs)\n"
        "\nclass OpenEnvRestoreResponse:\n"
        "    def __init__(self, **kwargs):\n"
        "        self.__dict__.update(kwargs)\n"
    )
    (repo / "affinetes" / "core" / "openenv.py").write_text(core_text, encoding="utf-8")
    (env_dir / "__init__.py").write_text("", encoding="utf-8")
    (env_dir / "requirements.txt").write_text("", encoding="utf-8")
    env_text = (
        "from dataclasses import dataclass\n"
        "\n"
        "@dataclass\n"
        "class Response:\n"
        "    observation: str = ''\n"
        "    episode_id: str = ''\n"
        "    checkpoint_id: str = ''\n"
        "    reward: float = 0.0\n"
        "    done: bool = False\n"
        "    truncated: bool = False\n"
        "    checkpoint_capable: bool = False\n"
        "    latest_checkpoint_id: str = ''\n"
        "    info: dict | None = None\n"
        "\n"
        "class InfiniteActor:\n"
        "    def __init__(self, api_key=None, cache_dir='/tmp/swe-infinite-cache', **kwargs):\n"
        "        self.api_key = api_key\n"
        "        self.cache_dir = cache_dir\n"
        "        self._episodes = {}\n"
        "\n"
        "    async def evaluate(self, task_id, model='m', base_url='u', api_key=None, timeout=0, temperature=0.0, seed=None, agent='', max_iterations=100, collect_logprobs=False):\n"
        "        print(f'upstream evaluate {task_id} {agent}')\n"
        "        success = str(task_id).endswith('1') or str(task_id).endswith('ok')\n"
        "        return {\n"
        "            'task_name': 'swe-infinite',\n"
        "            'score': 1.0 if success else 0.0,\n"
        "            'success': success,\n"
        "            'time_taken': 0.01,\n"
        "            'extra': {\n"
        "                'instance_id': str(task_id),\n"
        "                'fix_patch': 'diff --git a/x b/x\\n+pass\\n' if success else '',\n"
        "                'conversation': [{'role': 'user', 'content': 'prompt'}, {'role': 'assistant', 'content': 'done'}],\n"
        "                'test_stats': {'passed': ['test_ok'] if success else [], 'failed': [] if success else ['test_bad']},\n"
        "            },\n"
        "        }\n"
        "\n"
        "    async def reset(self, task_id, seed=None, step_limit=100, command_timeout=300):\n"
        "        episode_id = f'ep-{task_id}'\n"
        "        self._episodes[episode_id] = {'task_id': task_id, 'steps': 0}\n"
        "        return Response(observation=f'reset:{task_id}', episode_id=episode_id, done=False, truncated=False, info={'task_id': task_id, 'step_limit': step_limit})\n"
        "\n"
        "    async def step(self, action, episode_id=None):\n"
        "        ep = self._episodes[episode_id]\n"
        "        ep['steps'] += 1\n"
        "        return Response(observation=f'step:{action}', episode_id=episode_id, done=False, truncated=False, info={'steps': ep['steps']})\n"
        "\n"
        "    async def stop(self, episode_id=None):\n"
        "        self._episodes.pop(episode_id, None)\n"
        "        return {'status': 'ok', 'stopped': True, 'episode_id': episode_id}\n"
    )
    if support_checkpoint:
        env_text += (
            "\n    async def state(self, episode_id=None):\n"
            "        ep = self._episodes.get(episode_id)\n"
            "        return Response(observation=f'state:{episode_id}', episode_id=episode_id, done=False, truncated=False, checkpoint_capable=True, latest_checkpoint_id=ep.get('latest_checkpoint_id','') if ep else '', info={'steps': ep['steps'] if ep else 0})\n"
            "\n    async def checkpoint(self, episode_id=None, label=''):\n"
            "        ep = self._episodes[episode_id]\n"
            "        ckpt = f'ckpt-{ep[\"steps\"] + 1}'\n"
            "        ep['latest_checkpoint_id'] = ckpt\n"
            "        ep.setdefault('checkpoints', {})[ckpt] = {'steps': ep['steps'], 'label': label}\n"
            "        return Response(episode_id=episode_id, checkpoint_id=ckpt, info={'label': label})\n"
            "\n    async def restore(self, episode_id=None, checkpoint_id=''):\n"
            "        ep = self._episodes[episode_id]\n"
            "        ep['steps'] = ep['checkpoints'][checkpoint_id]['steps']\n"
            "        ep['latest_checkpoint_id'] = checkpoint_id\n"
            "        return Response(observation=f'restored:{checkpoint_id}', episode_id=episode_id, checkpoint_id=checkpoint_id, done=False, truncated=False, info={'steps': ep['steps']})\n"
        )
    env_text += "\nActor = InfiniteActor\n"
    (env_dir / "env.py").write_text(env_text, encoding="utf-8")

    _run(["git", "init"], cwd=repo)
    _run(["git", "config", "user.email", "test@example.com"], cwd=repo)
    _run(["git", "config", "user.name", "Test User"], cwd=repo)
    _run(["git", "add", "."], cwd=repo)
    _run(["git", "commit", "-m", "init"], cwd=repo)
    commit = _run(["git", "rev-parse", "HEAD"], cwd=repo)
    return repo, commit


class TestTaskParsing:
    def test_parse_task_range_supports_ranges_and_lists(self):
        assert parse_task_range("1-3,7,9-8") == ["1", "2", "3", "7", "9", "8"]


class TestSynthesisModelCalls:
    def test_chat_completion_falls_back_to_chat_completions_on_responses_404(self, monkeypatch):
        calls: list[str] = []

        class FakeNotFound(Exception):
            status_code = 404

        class FakeChoice:
            def model_dump(self, mode="json"):
                return {"message": {"content": "```bash\necho hello\n```"}}

        class FakeChatCompletions:
            def create(self, **kwargs):
                calls.append("chat")
                return type("Resp", (), {"id": "chat-id", "model": kwargs["model"], "choices": [FakeChoice()]})()

        class FakeResponses:
            def create(self, **kwargs):
                calls.append("responses")
                raise FakeNotFound("Not Found")

        class FakeClient:
            def __init__(self, **kwargs):
                self.responses = FakeResponses()
                self.chat = type("Chat", (), {"completions": FakeChatCompletions()})()

        monkeypatch.setattr(synthesis_module, "OpenAI", FakeClient)

        payload = synthesis_module._chat_completion(
            api_base="http://127.0.0.1:30000/v1",
            api_key="orbit-local",
            model="student-model",
            messages=[{"role": "user", "content": "echo"}],
            temperature=0.2,
            reasoning_effort="low",
            timeout=30,
        )

        assert calls == ["responses", "chat"]
        assert payload["model"] == "student-model"
        assert payload["choices"][0]["message"]["content"] == "```bash\necho hello\n```"


class TestUpstreamRuntime:
    def test_openenv_server_patches_startup_stale_cleanup_by_default(self, monkeypatch):
        class FakeActor:
            def _cleanup_stale_containers(self):
                return "original"

        monkeypatch.delenv("ORBIT_OPENENV_ALLOW_STARTUP_STALE_CLEANUP", raising=False)
        Patched = openenv_server_module._patch_actor_for_stateful_openenv_server(FakeActor)
        actor = Patched()
        assert actor._cleanup_stale_containers() is None

    def test_openenv_server_can_opt_in_to_startup_stale_cleanup(self, monkeypatch):
        class FakeActor:
            def _cleanup_stale_containers(self):
                return "original"

        monkeypatch.setenv("ORBIT_OPENENV_ALLOW_STARTUP_STALE_CLEANUP", "true")
        Patched = openenv_server_module._patch_actor_for_stateful_openenv_server(FakeActor)
        actor = Patched()
        assert actor._cleanup_stale_containers() == "original"

    def test_openenv_server_reuses_local_image_without_pull(self, monkeypatch):
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd))
            if cmd[:3] == ["docker", "image", "inspect"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")
            if cmd[:2] == ["docker", "run"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="container-id\n", stderr="")
            raise AssertionError(cmd)

        monkeypatch.setattr(openenv_server_module.subprocess, "run", fake_run)

        class FakeActor:
            def _start_container(self, docker_image: str, container_name: str) -> str:
                raise AssertionError("original _start_container should be replaced")

        Patched = openenv_server_module._patch_actor_for_local_image_reuse(FakeActor)
        actor = Patched()
        container_id = actor._start_container("example/image:tag", "ctr-name")

        assert container_id == "container-id"
        assert ["docker", "image", "inspect", "example/image:tag"] in calls
        assert not any(cmd[:2] == ["docker", "pull"] for cmd in calls)

    def test_openenv_server_retries_docker_run_with_longer_timeout(self, monkeypatch):
        calls: list[tuple[list[str], int | None]] = []
        run_attempts = {"count": 0}

        def fake_run(cmd, **kwargs):
            calls.append((list(cmd), kwargs.get("timeout")))
            if cmd[:3] == ["docker", "image", "inspect"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")
            if cmd[:3] == ["docker", "rm", "-f"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if cmd[:2] == ["docker", "run"]:
                run_attempts["count"] += 1
                if run_attempts["count"] == 1:
                    raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout") or 0)
                return subprocess.CompletedProcess(cmd, 0, stdout="container-id\n", stderr="")
            raise AssertionError(cmd)

        monkeypatch.setenv("ORBIT_OPENENV_DOCKER_RUN_TIMEOUT_SECS", "123")
        monkeypatch.setenv("ORBIT_OPENENV_DOCKER_RUN_RETRIES", "2")
        monkeypatch.setenv("ORBIT_OPENENV_DOCKER_RUN_RETRY_DELAY_SECS", "0")
        monkeypatch.setattr(openenv_server_module.subprocess, "run", fake_run)
        monkeypatch.setattr(openenv_server_module.time, "sleep", lambda *_args, **_kwargs: None)

        class FakeActor:
            def _start_container(self, docker_image: str, container_name: str) -> str:
                raise AssertionError("original _start_container should be replaced")

        Patched = openenv_server_module._patch_actor_for_local_image_reuse(FakeActor)
        actor = Patched()
        container_id = actor._start_container("example/image:tag", "ctr-name")

        assert container_id == "container-id"
        run_timeouts = [timeout for cmd, timeout in calls if cmd[:2] == ["docker", "run"]]
        assert run_timeouts == [123, 123]
        assert any(cmd[:3] == ["docker", "rm", "-f"] for cmd, _timeout in calls)

    def test_prewarm_swe_task_images_dedupes_and_skips_cached_images(self, monkeypatch, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / "task_00000000001.json").write_text(json.dumps({"dockerhub_tag": "repo:image-a"}), encoding="utf-8")
        (cache_dir / "task_00000000002.json").write_text(json.dumps({"dockerhub_tag": "repo:image-a"}), encoding="utf-8")
        (cache_dir / "task_00000000003.json").write_text(json.dumps({"dockerhub_tag": "repo:image-b"}), encoding="utf-8")
        selected = tmp_path / "selected_tasks.json"
        selected.write_text(
            json.dumps(
                {
                    "selected_tasks": [
                        {"task_id": 1, "instance_id": "a"},
                        {"task_id": 2, "instance_id": "b"},
                        {"task_id": 3, "instance_id": "c"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        output = tmp_path / "prewarm.json"
        inspect_results = {
            "affinefoundation/swe_infinite_images:image-a": True,
            "affinefoundation/swe_infinite_images:image-b": False,
        }
        pulls: list[str] = []

        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["docker", "image", "inspect"]:
                image = cmd[3]
                return subprocess.CompletedProcess(cmd, 0 if inspect_results[image] else 1, stdout="", stderr="")
            if cmd[:2] == ["docker", "pull"]:
                pulls.append(cmd[2])
                return subprocess.CompletedProcess(cmd, 0, stdout="pulled", stderr="")
            raise AssertionError(cmd)

        monkeypatch.setattr(runner_module, "_run", fake_run)
        monkeypatch.setattr(runner_module.time, "sleep", lambda *_args, **_kwargs: None)

        payload = runner_module.prewarm_swe_task_images(
            selected_tasks_json=str(selected),
            cache_dir=str(cache_dir),
            output_path=str(output),
            pull_timeout_secs=123,
            pull_concurrency=2,
            pull_retries=2,
        )

        assert payload["unique_image_count"] == 2
        assert pulls == ["affinefoundation/swe_infinite_images:image-b"]
        statuses = {item["image"]: item["status"] for item in payload["images"]}
        assert statuses == {
            "affinefoundation/swe_infinite_images:image-a": "cached",
            "affinefoundation/swe_infinite_images:image-b": "pulled",
        }
        saved = json.loads(output.read_text(encoding="utf-8"))
        assert saved["unique_image_count"] == 2

    def test_pull_task_image_returns_retryable_failed_on_inspect_timeout(self, monkeypatch):
        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["docker", "image", "inspect"]:
                raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout") or 0)
            raise AssertionError(cmd)

        monkeypatch.setattr(runner_module, "_run", fake_run)
        monkeypatch.setattr(runner_module.time, "sleep", lambda *_args, **_kwargs: None)

        result = runner_module._pull_task_image(
            image="repo:image-timeout",
            timeout_secs=1800,
            retries=3,
            inspect_timeout_secs=7,
            inspect_retries=2,
        )

        assert result["status"] == "retryable_failed"
        assert "timed out" in result["error"]

    def test_pull_task_image_returns_retryable_failed_on_pull_timeout(self, monkeypatch):
        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["docker", "image", "inspect"]:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
            if cmd[:2] == ["docker", "pull"]:
                raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout") or 0)
            raise AssertionError(cmd)

        monkeypatch.setattr(runner_module, "_run", fake_run)
        monkeypatch.setattr(runner_module.time, "sleep", lambda *_args, **_kwargs: None)

        result = runner_module._pull_task_image(
            image="repo:image-pull-timeout",
            timeout_secs=9,
            retries=2,
            inspect_timeout_secs=7,
            inspect_retries=1,
        )

        assert result["status"] == "retryable_failed"
        assert "timed out" in result["error"]

    def test_openenv_server_socket_path_is_short(self, tmp_path):
        output_dir = tmp_path / ("nested-" * 12) / "run"
        socket_path = _server_socket_path(str(output_dir))
        assert str(socket_path).startswith("/tmp/orbit-openenv-")
        assert len(str(socket_path)) < 100

    def test_prepare_upstream_runtime_accepts_clean_repo(self, monkeypatch, tmp_path):
        repo, commit = _init_fake_affinetes_repo(tmp_path)
        monkeypatch.setattr(runner_module, "DEFAULT_SHARED_RUNTIME_CACHE_ROOT", str(tmp_path / "shared-cache"))

        prepared = prepare_upstream_runtime(
            output_dir=str(tmp_path / "run"),
            upstream_repo_path=str(repo),
            upstream_ref=commit,
        )

        assert prepared.repo_root == repo.resolve()
        assert prepared.upstream_ref == commit
        assert prepared.python_bin.exists()

    def test_prepare_upstream_runtime_rejects_dirty_repo(self, monkeypatch, tmp_path):
        repo, commit = _init_fake_affinetes_repo(tmp_path)
        monkeypatch.setattr(runner_module, "DEFAULT_SHARED_RUNTIME_CACHE_ROOT", str(tmp_path / "shared-cache"))
        (repo / "dirty.txt").write_text("x\n", encoding="utf-8")

        try:
            prepare_upstream_runtime(
                output_dir=str(tmp_path / "run"),
                upstream_repo_path=str(repo),
                upstream_ref=commit,
            )
        except RuntimeError as exc:
            assert "dirty" in str(exc)
        else:
            raise AssertionError("expected dirty upstream repo to fail")

    def test_prepare_upstream_runtime_clone_mode_uses_exact_ref(self, monkeypatch, tmp_path):
        repo, commit = _init_fake_affinetes_repo(tmp_path)
        monkeypatch.setattr(runner_module, "DEFAULT_SHARED_RUNTIME_CACHE_ROOT", str(tmp_path / "shared-cache"))

        prepared = prepare_upstream_runtime(
            output_dir=str(tmp_path / "run"),
            upstream_git_url=str(repo),
            upstream_ref=commit,
        )

        assert prepared.repo_root.exists()
        assert (prepared.repo_root / "environments" / "SWE-INFINITE" / "env.py").exists()

    def test_prepare_upstream_runtime_reuses_shared_runtime_cache(self, monkeypatch, tmp_path):
        repo, commit = _init_fake_affinetes_repo(tmp_path)
        monkeypatch.setattr(runner_module, "DEFAULT_SHARED_RUNTIME_CACHE_ROOT", str(tmp_path / "shared-cache"))

        prepared_one = prepare_upstream_runtime(
            output_dir=str(tmp_path / "run-a"),
            upstream_repo_path=str(repo),
            upstream_ref=commit,
        )
        prepared_two = prepare_upstream_runtime(
            output_dir=str(tmp_path / "run-b"),
            upstream_repo_path=str(repo),
            upstream_ref=commit,
        )

        assert prepared_one.python_bin == prepared_two.python_bin
        assert prepared_one.runtime_dir != prepared_two.runtime_dir
        assert prepared_one.python_bin.exists()

    def test_server_env_sets_docker_run_defaults(self, monkeypatch, tmp_path):
        repo, commit = _init_fake_affinetes_repo(tmp_path)
        monkeypatch.setattr(runner_module, "DEFAULT_SHARED_RUNTIME_CACHE_ROOT", str(tmp_path / "shared-cache"))

        prepared = prepare_upstream_runtime(
            output_dir=str(tmp_path / "run"),
            upstream_repo_path=str(repo),
            upstream_ref=commit,
        )

        env = runner_module._server_env(prepared, tmp_path / "home")

        assert env["ORBIT_OPENENV_DOCKER_RUN_TIMEOUT_SECS"] == "180"
        assert env["ORBIT_OPENENV_DOCKER_RUN_RETRIES"] == "2"
        assert env["ORBIT_OPENENV_DOCKER_RUN_RETRY_DELAY_SECS"] == "3"

    def test_ensure_requirements_bootstraps_pip_with_ensurepip(self, monkeypatch, tmp_path):
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd))
            if cmd[-2:] == ["pip", "--version"]:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="No module named pip")
            if cmd[-2:] == ["ensurepip", "--upgrade"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="bootstrapped", stderr="")
            if cmd[1:4] == ["-m", "pip", "install"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="installed", stderr="")
            raise AssertionError(cmd)

        monkeypatch.setattr(runner_module, "_run", fake_run)
        monkeypatch.setattr(runner_module, "_python_version", lambda _python_bin: "3.12.0")

        requirements = tmp_path / "requirements.txt"
        requirements.write_text("requests==2.0.0\n", encoding="utf-8")
        stamp = tmp_path / "requirements.stamp"
        runner_module._ensure_requirements(Path("/fake/python"), requirements, stamp, "a" * 40)

        assert any(cmd[-2:] == ["ensurepip", "--upgrade"] for cmd in calls)
        assert any(cmd[1:4] == ["-m", "pip", "install"] for cmd in calls)
        assert stamp.exists()


class TestBatchLauncher:
    def test_batch_launcher_rejects_duplicate_task_ids(self, tmp_path):
        selected = tmp_path / "selected_tasks.json"
        selected.write_text(
            json.dumps({"selected_tasks": [{"task_id": 1}, {"task_id": 1}]}),
            encoding="utf-8",
        )

        with pytest.raises(RuntimeError, match="duplicate task_id"):
            batch_launcher_module._selected_tasks(selected)

    def test_batch_launcher_rejects_incomplete_prewarm_manifest(self, tmp_path):
        manifest = tmp_path / "image_prewarm.json"
        manifest.write_text(
            json.dumps({"images": [{"image": "repo:image", "status": "failed"}]}),
            encoding="utf-8",
        )

        with pytest.raises(RuntimeError, match="non-ready images"):
            batch_launcher_module._validate_prewarm_manifest(manifest)

    def test_cleanup_orphan_openenv_server_terminates_pid(self, monkeypatch, tmp_path):
        output_dir = tmp_path / "task"
        meta_path = output_dir / ".runtime" / "openenv_server.json"
        meta_path.parent.mkdir(parents=True)
        socket_path = tmp_path / "openenv.sock"
        socket_path.write_text("", encoding="utf-8")
        meta_path.write_text(json.dumps({"pid": 4321, "socket_path": str(socket_path)}), encoding="utf-8")
        killed: list[tuple[int, int]] = []

        monkeypatch.setattr(batch_launcher_module.os, "kill", lambda pid, sig: killed.append((pid, sig)))

        assert batch_launcher_module.cleanup_orphan_openenv_server(output_dir) is True
        assert killed == [(4321, signal.SIGTERM)]
        assert not meta_path.exists()
        assert not socket_path.exists()

    def test_ready_gate_rejects_missing_log_ready_marker(self, monkeypatch):
        monkeypatch.setattr(
            batch_launcher_module,
            "_http_json",
            lambda method, url, payload=None, timeout=30: (
                {"data": [{"id": "Qwen/Qwen3.6-35B-A3B"}]}
                if url.endswith("/models")
                else {"ok": True}
                if url.endswith("/model_info")
                else {"choices": [{"message": {"content": "OK"}}]}
            ),
        )
        monkeypatch.setattr(batch_launcher_module, "_ssh_read_text", lambda **kwargs: "still capturing")
        monkeypatch.setattr(batch_launcher_module.time, "sleep", lambda *_args, **_kwargs: None)

        with pytest.raises(RuntimeError, match="ready gate failed"):
            batch_launcher_module.ready_gate(
                api_base="http://127.0.0.1:30001/v1",
                model="Qwen/Qwen3.6-35B-A3B",
                timeout_secs=0,
                student_log_path="/root/logs/sglang.log",
                student_ssh_host="127.0.0.1",
                student_ssh_port=22,
            )

    def test_release_warm_ready_runs_creates_release_file(self, tmp_path):
        run = batch_launcher_module.TaskRun(
            task_id="1",
            status="warm_ready",
            output_dir=tmp_path / "task-1",
            rollout_release_file=tmp_path / "task-1" / ".runtime" / "rollout_release.json",
        )
        runs = {"1": run}

        released = batch_launcher_module._release_warm_ready_runs(runs, max_live_rollouts=1)

        assert released == 1
        assert run.rollout_released is True
        assert run.rollout_release_file.exists()

    def test_rollout_slot_usage_counts_released_warm_ready(self, tmp_path):
        warm = batch_launcher_module.TaskRun(
            task_id="1",
            status="warm_ready",
            output_dir=tmp_path / "task-1",
            rollout_released=True,
        )
        running = batch_launcher_module.TaskRun(task_id="2", status="running")
        boot = batch_launcher_module.TaskRun(task_id="3", status="bootstrapping")
        runs = {"1": warm, "2": running, "3": boot}

        assert batch_launcher_module._rollout_slot_usage(runs) == 2
        assert batch_launcher_module._inflight_task_count(runs) == 3
        assert batch_launcher_module._warm_ready_count(runs) == 1

    def test_ready_pending_count_only_counts_ready_images(self):
        runs = {
            "1": batch_launcher_module.TaskRun(task_id="1", image="img-ready", status="pending"),
            "2": batch_launcher_module.TaskRun(task_id="2", image="img-pulling", status="pending"),
            "3": batch_launcher_module.TaskRun(task_id="3", image="img-failed", status="pending"),
            "4": batch_launcher_module.TaskRun(task_id="4", image="img-running", status="running"),
        }
        image_states = {
            "img-ready": batch_launcher_module.ImagePullState("img-ready", status="ready"),
            "img-pulling": batch_launcher_module.ImagePullState("img-pulling", status="pulling"),
            "img-failed": batch_launcher_module.ImagePullState("img-failed", status="failed"),
        }

        assert batch_launcher_module._ready_pending_count(runs, image_states) == 1

    def test_prefetched_pending_count_includes_pulling_images(self):
        runs = {
            "1": batch_launcher_module.TaskRun(task_id="1", image="img-ready", status="pending"),
            "2": batch_launcher_module.TaskRun(task_id="2", image="img-pulling", status="pending"),
            "3": batch_launcher_module.TaskRun(task_id="3", image="img-failed", status="pending"),
            "4": batch_launcher_module.TaskRun(task_id="4", image="img-completed", status="completed"),
        }
        image_states = {
            "img-ready": batch_launcher_module.ImagePullState("img-ready", status="ready"),
            "img-pulling": batch_launcher_module.ImagePullState("img-pulling", status="pulling"),
            "img-failed": batch_launcher_module.ImagePullState("img-failed", status="failed"),
        }

        assert batch_launcher_module._prefetched_pending_count(runs, image_states) == 2

    def test_refresh_image_pull_queue_adds_unique_frontier_images(self):
        runs = {
            "1": batch_launcher_module.TaskRun(task_id="1", image="img-a", status="pending"),
            "2": batch_launcher_module.TaskRun(task_id="2", image="img-a", status="pending"),
            "3": batch_launcher_module.TaskRun(task_id="3", image="img-b", status="pending"),
            "4": batch_launcher_module.TaskRun(task_id="4", image="img-c", status="running"),
        }
        image_states = {
            "img-a": batch_launcher_module.ImagePullState("img-a", status="pending"),
            "img-b": batch_launcher_module.ImagePullState("img-b", status="pending"),
            "img-c": batch_launcher_module.ImagePullState("img-c", status="ready"),
        }
        queue = deque()
        queued = set()

        batch_launcher_module._refresh_image_pull_queue(
            queue,
            queued,
            ordered_task_ids=["1", "2", "3", "4"],
            runs=runs,
            image_states=image_states,
            prefetch_target=3,
        )

        assert list(queue) == ["img-a", "img-b"]
        assert queued == {"img-a", "img-b"}

    def test_refresh_bootstrap_queue_adds_ready_pending_tasks_only(self):
        runs = {
            "1": batch_launcher_module.TaskRun(task_id="1", image="img-a", status="pending"),
            "2": batch_launcher_module.TaskRun(task_id="2", image="img-b", status="pending"),
            "3": batch_launcher_module.TaskRun(task_id="3", image="img-c", status="bootstrapping"),
            "4": batch_launcher_module.TaskRun(task_id="4", image="img-d", status="pending"),
        }
        image_states = {
            "img-a": batch_launcher_module.ImagePullState("img-a", status="ready"),
            "img-b": batch_launcher_module.ImagePullState("img-b", status="pulling"),
            "img-c": batch_launcher_module.ImagePullState("img-c", status="ready"),
            "img-d": batch_launcher_module.ImagePullState("img-d", status="ready"),
        }
        queue = deque(["4"])
        queued = {"4"}

        batch_launcher_module._refresh_bootstrap_queue(
            queue,
            queued,
            ordered_task_ids=["1", "2", "3", "4"],
            runs=runs,
            image_states=image_states,
        )

        assert list(queue) == ["4", "1"]
        assert queued == {"4", "1"}


class TestBlackBoxEvaluate:
    def test_run_affinetes_swe_evaluate_writes_raw_outputs(self, tmp_path):
        repo, commit = _init_fake_affinetes_repo(tmp_path)

        result = run_affinetes_swe_evaluate(
            task_range="1-2",
            output_dir=str(tmp_path / "run"),
            upstream_repo_path=str(repo),
            upstream_ref=commit,
            agent="miniswe",
            model="demo-model",
            api_key="token",
        )

        manifest = json.loads((tmp_path / "run" / "manifests" / "run.json").read_text(encoding="utf-8"))
        task_one = tmp_path / "run" / "raw" / "1" / "upstream_result.json"
        task_two = tmp_path / "run" / "raw" / "2" / "upstream_result.json"
        assert result.records == 2
        assert result.success == 1
        assert task_one.exists()
        assert task_two.exists()
        assert (tmp_path / "run" / "raw" / "1" / "conversation.json").exists()
        assert manifest["upstream_ref"] == commit
        assert manifest["agent"] == "miniswe"
        assert manifest["task_count"] == 2

    def test_resume_uses_existing_result_files(self, tmp_path):
        repo, commit = _init_fake_affinetes_repo(tmp_path)
        output_dir = tmp_path / "run"

        first = run_affinetes_swe_evaluate(
            task_range="1",
            output_dir=str(output_dir),
            upstream_repo_path=str(repo),
            upstream_ref=commit,
            agent="miniswe",
            model="demo-model",
            api_key="token",
        )
        second = run_affinetes_swe_evaluate(
            task_range="1",
            output_dir=str(output_dir),
            upstream_repo_path=str(repo),
            upstream_ref=commit,
            agent="miniswe",
            model="demo-model",
            api_key="token",
            resume=True,
        )

        assert first.records == 1
        assert second.records == 1
        manifest = json.loads((output_dir / "manifests" / "run.json").read_text(encoding="utf-8"))
        assert manifest["tasks"][0]["resumed"] is True

    def test_collect_swe_adapter_writes_staging_manifest(self, tmp_path):
        repo, commit = _init_fake_affinetes_repo(tmp_path)
        config = SweCollectConfig(
            upstream_repo_path=str(repo),
            upstream_ref=commit,
            mode="evaluate",
            agent="miniswe",
            task_range="1",
            model="demo-model",
            api_key="token",
            output_dir=str(tmp_path / "run"),
        )

        result = collect_swe(config, str(tmp_path / "canonical"), str(tmp_path / "raw"), str(tmp_path / "staging" / "swe.json"))

        assert result.records == 1
        assert Path(result.staging_path).exists()
        assert json.loads(Path(result.staging_path).read_text(encoding="utf-8"))["task_count"] == 1


class TestOpenEnvBridge:
    def test_openenv_reset_step_stop_roundtrip(self, tmp_path):
        repo, commit = _init_fake_affinetes_repo(tmp_path)
        output_dir = tmp_path / "openenv"

        reset = openenv_reset(
            output_dir=str(output_dir),
            upstream_repo_path=str(repo),
            upstream_ref=commit,
            api_key="token",
            task_id="demo-task",
        )
        step = openenv_step(
            output_dir=str(output_dir),
            action_text="```bash\nls\n```",
        )
        stop = openenv_stop(output_dir=str(output_dir))

        assert reset["episode_id"] == "ep-demo-task"
        assert step["info"]["steps"] == 1
        assert stop["stopped"] is True
        assert not (output_dir / ".runtime" / "openenv_server.json").exists()

    def test_openenv_state_checkpoint_restore_roundtrip(self, tmp_path):
        repo, commit = _init_fake_affinetes_repo(tmp_path)
        output_dir = tmp_path / "openenv"

        reset = openenv_reset(
            output_dir=str(output_dir),
            upstream_repo_path=str(repo),
            upstream_ref=commit,
            api_key="token",
            task_id="demo-task",
        )
        checkpoint = openenv_checkpoint(output_dir=str(output_dir), label="before")
        state = openenv_state(output_dir=str(output_dir))
        step = openenv_step(output_dir=str(output_dir), action_text="```bash\nls\n```")
        restored = openenv_restore(output_dir=str(output_dir), checkpoint_id=checkpoint["checkpoint_id"])
        stop = openenv_stop(output_dir=str(output_dir))

        assert reset["episode_id"] == "ep-demo-task"
        assert checkpoint["checkpoint_id"] == "ckpt-1"
        assert state["checkpoint_capable"] is True
        assert state["latest_checkpoint_id"] == "ckpt-1"
        assert step["info"]["steps"] == 1
        assert restored["observation"] == "restored:ckpt-1"
        assert restored["info"]["steps"] == 0
        assert stop["stopped"] is True

    def test_openenv_reset_reuses_output_dir_after_stop(self, tmp_path):
        repo, commit = _init_fake_affinetes_repo(tmp_path)
        output_dir = tmp_path / "openenv"

        first = openenv_reset(
            output_dir=str(output_dir),
            upstream_repo_path=str(repo),
            upstream_ref=commit,
            api_key="token",
            task_id="demo-task",
        )
        stopped = openenv_stop(output_dir=str(output_dir), episode_id=first["episode_id"])
        second = openenv_reset(
            output_dir=str(output_dir),
            upstream_repo_path=str(repo),
            upstream_ref=commit,
            api_key="token",
            task_id="demo-task",
        )

        assert stopped["stopped"] is True
        assert second["episode_id"] == "ep-demo-task"

    def test_openenv_checkpoint_restore_unsupported_for_env_without_methods(self, tmp_path):
        repo, commit = _init_fake_affinetes_repo(tmp_path, support_checkpoint=False)
        output_dir = tmp_path / "openenv"

        reset = openenv_reset(
            output_dir=str(output_dir),
            upstream_repo_path=str(repo),
            upstream_ref=commit,
            api_key="token",
            task_id="demo-task",
        )
        state = openenv_state(output_dir=str(output_dir))
        checkpoint = openenv_checkpoint(output_dir=str(output_dir))
        restored = openenv_restore(output_dir=str(output_dir), checkpoint_id="ckpt-1")
        stop = openenv_stop(output_dir=str(output_dir))

        assert reset["episode_id"] == "ep-demo-task"
        assert state["info"]["error"]["type"] == "unsupported_operation"
        assert checkpoint["info"]["error"]["type"] == "unsupported_operation"
        assert restored["info"]["error"]["type"] == "unsupported_operation"
        assert stop["stopped"] is True


class TestOpenEnvSynthesis:
    def test_runtime_preference_uses_perl_before_python2(self):
        assert synthesis_module._preferred_runtime_from_availability(
            {"python3": False, "python": True, "ruby": False, "perl": True}
        ) == "perl"

    def test_perl_runtime_rejects_python_commands(self):
        rejected, runtime = synthesis_module._command_uses_unavailable_runtime(
            "python - <<'PY'\nprint('x')\nPY",
            "perl",
        )
        assert rejected is True
        assert runtime == "python"

    def test_synthesis_restores_baseline_after_no_progress(self, monkeypatch, tmp_path):
        calls: list[tuple[str, dict]] = []
        state_counter = {"value": 0}

        def fake_reset(**kwargs):
            calls.append(("reset", kwargs))
            return {"episode_id": "ep-1", "observation": "solve bug", "done": False, "truncated": False}

        def fake_checkpoint(**kwargs):
            calls.append(("checkpoint", kwargs))
            label = kwargs.get("label") or "baseline"
            return {"episode_id": "ep-1", "checkpoint_id": f"{label}-ckpt"}

        def fake_step(**kwargs):
            calls.append(("step", kwargs))
            if "retry action" in kwargs["action_text"]:
                return {
                    "episode_id": "ep-1",
                    "observation": "<returncode>0</returncode><output>edited</output>",
                    "done": True,
                    "truncated": False,
                    "reward": 1.0,
                    "info": {"test_stats": {"passed": 2, "failed": 0}},
                }
            return {"episode_id": "ep-1", "observation": "<returncode>0</returncode><output>noop</output>", "done": False, "truncated": False}

        def fake_state(**kwargs):
            calls.append(("state", kwargs))
            state_counter["value"] += 1
            if state_counter["value"] == 1:
                return {"episode_id": "ep-1", "observation": "state-no-progress", "info": {"changed_files": []}}
            return {"episode_id": "ep-1", "observation": "state-progress", "info": {"changed_files": ["app.py"]}}

        def fake_restore(**kwargs):
            calls.append(("restore", kwargs))
            return {"episode_id": "ep-1", "observation": "restored baseline"}

        def fake_stop(**kwargs):
            calls.append(("stop", kwargs))
            return {"episode_id": "ep-1", "stopped": True}

        responses = iter(["```bash\ncd /app && ls\n```", "```bash\necho retry action\n```"])

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_reset", fake_reset)
        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint", fake_checkpoint)
        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_step", fake_step)
        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_state", fake_state)
        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_restore", fake_restore)
        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_stop", fake_stop)
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._chat_completion",
            lambda **kwargs: {"choices": [{"message": {"content": next(responses)}}]},
        )

        result = run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="teacher-model",
            api_key="token",
            max_steps=2,
            max_root_retries=1,
            max_edit_retries=0,
        )

        assert result["baseline_checkpoint_id"] == "baseline-ckpt"
        assert result["root_retries_used"] == 1
        assert result["latest_changed_files"] == ["app.py"]
        assert result["final_reward"] == 1.0
        assert result["verified_success"] is True
        assert result["final_test_stats"] == {"passed": 2, "failed": 0}
        assert any(kind == "restore" for kind, _ in calls)
        manifest = json.loads((tmp_path / "synth" / "manifests" / "synthesis_run.json").read_text(encoding="utf-8"))
        assert manifest["root_retries_used"] == 1
        assert manifest["final_reward"] == 1.0
        assert manifest["verified_success"] is True

    def test_synthesis_normalizes_multi_block_model_output(self, monkeypatch, tmp_path):
        observed_actions: list[str] = []

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "prompt", "done": False, "truncated": False},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"},
        )

        def fake_step(**kwargs):
            observed_actions.append(kwargs["action_text"])
            return {"episode_id": "ep-1", "observation": "ok", "done": True, "truncated": False}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_step", fake_step)
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "state", "info": {"changed_files": []}},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._chat_completion",
            lambda **kwargs: {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "THOUGHT: inspect\n\n```bash\ncd /app && ls\n```\n"
                                "THOUGHT: search\n\n```bash\ncd /app && rg foo\n```"
                            )
                        }
                    }
                ]
            },
        )

        run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="teacher-model",
            api_key="token",
            max_steps=1,
        )

        assert observed_actions == ["```bash\ncd /app && rg foo\n```"]

    def test_synthesis_retries_retryable_baseline_checkpoint_failure(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {
                "episode_id": "ep-1",
                "observation": "<pr_description>fix issue</pr_description>",
                "done": False,
                "truncated": False,
            },
        )

        checkpoint_calls = {"value": 0}

        def fake_checkpoint(**kwargs):
            checkpoint_calls["value"] += 1
            if checkpoint_calls["value"] == 1:
                return {
                    "episode_id": "ep-1",
                    "checkpoint_id": "",
                    "info": {
                        "error": {
                            "type": "checkpoint_failed",
                            "message": "failed to capture file snapshot: No such container: deadbeef",
                            "retryable": True,
                        }
                    },
                }
            return {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint", fake_checkpoint)
        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.time.sleep", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._chat_completion",
            lambda **kwargs: {
                "choices": [
                    {
                        "message": {
                            "content": "THOUGHT: done\n\n```bash\necho COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git add -A && git diff --cached\n```"
                        }
                    }
                ]
            },
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_step",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "submitted", "done": True, "truncated": False, "reward": 0.0},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "state", "info": {"changed_files": []}},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )

        result = run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="student-model",
            api_key="token",
            max_steps=1,
        )

        assert checkpoint_calls["value"] == 2
        assert result["baseline_checkpoint_id"] == "baseline-ckpt"
        events = (tmp_path / "synth" / "raw" / "synthesis_events.jsonl").read_text(encoding="utf-8").splitlines()
        checkpoint_events = [json.loads(line) for line in events if json.loads(line).get("kind") == "checkpoint"]
        assert [event.get("attempt") for event in checkpoint_events[:2]] == [1, 2]
        assert all(event.get("reset_attempt") == 1 for event in checkpoint_events[:2])

    def test_synthesis_restarts_episode_after_exhausting_retryable_baseline_checkpoint_attempts(self, monkeypatch, tmp_path):
        reset_calls = {"value": 0}

        def fake_reset(**kwargs):
            reset_calls["value"] += 1
            episode_id = f"ep-{reset_calls['value']}"
            return {
                "episode_id": episode_id,
                "observation": "<pr_description>fix issue</pr_description>",
                "done": False,
                "truncated": False,
            }

        checkpoint_calls = {"value": 0}

        def fake_checkpoint(**kwargs):
            checkpoint_calls["value"] += 1
            if checkpoint_calls["value"] <= 3:
                return {
                    "episode_id": kwargs["episode_id"],
                    "checkpoint_id": "",
                    "info": {
                        "error": {
                            "type": "checkpoint_failed",
                            "message": "failed to capture file snapshot: No such container: deadbeef",
                            "retryable": True,
                        }
                    },
                }
            return {"episode_id": kwargs["episode_id"], "checkpoint_id": "baseline-ckpt"}

        stop_calls: list[str] = []

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_reset", fake_reset)
        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint", fake_checkpoint)
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: stop_calls.append(kwargs["episode_id"]) or {"episode_id": kwargs["episode_id"], "stopped": True},
        )
        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.time.sleep", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._chat_completion",
            lambda **kwargs: {
                "choices": [
                    {
                        "message": {
                            "content": "THOUGHT: done\n\n```bash\necho COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git add -A && git diff --cached\n```"
                        }
                    }
                ]
            },
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_step",
            lambda **kwargs: {"episode_id": kwargs["episode_id"], "observation": "submitted", "done": True, "truncated": False, "reward": 0.0},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: {"episode_id": kwargs["episode_id"], "observation": "state", "info": {"changed_files": []}},
        )

        result = run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="student-model",
            api_key="token",
            max_steps=1,
        )

        assert reset_calls["value"] == 2
        assert checkpoint_calls["value"] == 4
        assert stop_calls == ["ep-1", "ep-2"]
        assert result["episode_id"] == "ep-2"
        assert result["baseline_checkpoint_id"] == "baseline-ckpt"
        events = (tmp_path / "synth" / "raw" / "synthesis_events.jsonl").read_text(encoding="utf-8").splitlines()
        parsed = [json.loads(line) for line in events]
        reset_events = [event for event in parsed if event.get("kind") == "reset"]
        checkpoint_events = [event for event in parsed if event.get("kind") == "checkpoint"]
        stop_events = [event for event in parsed if event.get("kind") == "stop" and event.get("scope") == "baseline_retry_cleanup"]
        assert [event.get("attempt") for event in reset_events] == [1, 2]
        assert [event.get("reset_attempt") for event in checkpoint_events] == [1, 1, 1, 2]
        assert len(stop_events) == 1

    def test_synthesis_prefers_last_bash_block_over_trailing_submit_token(self, monkeypatch, tmp_path):
        observed_actions: list[str] = []

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "prompt", "done": False, "truncated": False},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"},
        )

        def fake_step(**kwargs):
            observed_actions.append(kwargs["action_text"])
            return {"episode_id": "ep-1", "observation": "ok", "done": True, "truncated": False}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_step", fake_step)
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "state", "info": {"changed_files": []}},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._chat_completion",
            lambda **kwargs: {
                "output_text": (
                    "```bash\ncd /app && git grep -n \"BlockDelimiters\"\n```"
                    "```bash\ncd /app && sed -n '1,40p' lib/rubocop/cop/style/block_delimiters.rb\n```"
                    "<SUBMIT>"
                )
            },
        )

        run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="teacher-model",
            api_key="token",
            max_steps=1,
        )

        assert observed_actions == ["```bash\ncd /app && sed -n '1,40p' lib/rubocop/cop/style/block_delimiters.rb\n```"]

    def test_synthesis_materializes_submit_token_to_upstream_command(self, monkeypatch, tmp_path):
        observed_actions: list[str] = []

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "prompt", "done": False, "truncated": False},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"},
        )

        def fake_step(**kwargs):
            observed_actions.append(kwargs["action_text"])
            return {"episode_id": "ep-1", "observation": "done", "done": True, "truncated": False}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_step", fake_step)
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: {
                "episode_id": "ep-1",
                "observation": "state",
                "info": {"changed_files": ["release_notes.py"], "last_patch_hash": "abc"},
            },
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._chat_completion",
            lambda **kwargs: {"output_text": "<SUBMIT>"},
        )

        run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="teacher-model",
            api_key="token",
            max_steps=1,
        )

        assert observed_actions == ["```bash\necho COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git add -A && git diff --cached\n```"]

    def test_synthesis_prefers_search_block_before_any_file_is_viewed(self, monkeypatch, tmp_path):
        observed_actions: list[str] = []

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "prompt", "done": False, "truncated": False},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"},
        )

        def fake_step(**kwargs):
            observed_actions.append(kwargs["action_text"])
            return {"episode_id": "ep-1", "observation": "ok", "done": True, "truncated": False}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_step", fake_step)
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "state", "info": {"changed_files": []}},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._chat_completion",
            lambda **kwargs: {
                "output_text": (
                    "```bash\ncd /app && git grep -n \"BlockDelimiters\" lib spec config\n```"
                    "```bash\ncd /app && ruby - <<'RUBY'\nputs 'edit'\nRUBY\n```"
                    "```bash\ncd /app && bundle exec rspec spec/rubocop/cop/style/block_delimiters_spec.rb\n```"
                )
            },
        )

        run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="teacher-model",
            api_key="token",
            max_steps=1,
        )

        assert observed_actions == ["```bash\ncd /app && git grep -n \"BlockDelimiters\" lib spec config\n```"]

    def test_synthesis_prefers_file_view_after_search_finds_candidate_file(self, monkeypatch, tmp_path):
        observed_actions: list[str] = []
        responses = iter(
            [
                "```bash\ncd /app && git grep -n \"BlockDelimiters\" lib spec config\n```",
                (
                    "```bash\ncd /app && git grep -n \"line_count_based\" lib spec config\n```"
                    "```bash\ncd /app && sed -n '120,180p' lib/rubocop/cop/style/block_delimiters.rb\n```"
                    "```bash\ncd /app && bundle exec rspec spec/rubocop/cop/style/block_delimiters_spec.rb\n```"
                ),
            ]
        )

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "prompt", "done": False, "truncated": False},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"},
        )

        def fake_step(**kwargs):
            observed_actions.append(kwargs["action_text"])
            if len(observed_actions) == 1:
                return {
                    "episode_id": "ep-1",
                    "observation": "<returncode>0</returncode>\n<output>\nlib/rubocop/cop/style/block_delimiters.rb:130:def on_block(node)\n</output>",
                    "done": False,
                    "truncated": False,
                }
            return {"episode_id": "ep-1", "observation": "ok", "done": True, "truncated": False}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_step", fake_step)
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "state", "info": {"changed_files": []}},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._chat_completion",
            lambda **kwargs: {"output_text": next(responses)},
        )

        run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="teacher-model",
            api_key="token",
            max_steps=2,
        )

        assert observed_actions == [
            "```bash\ncd /app && git grep -n \"BlockDelimiters\" lib spec config\n```",
            "```bash\ncd /app && sed -n '120,180p' lib/rubocop/cop/style/block_delimiters.rb\n```",
        ]

    def test_synthesis_retry_prompt_discourages_repeating_no_progress_commands(self, monkeypatch, tmp_path):
        prompts: list[list[dict[str, str]]] = []
        responses = iter(["```bash\ncd /app && ls\n```", "```bash\ncd /app && rg -n \"BlockDelimiters\" lib spec\n```"])

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {
                "episode_id": "ep-1",
                "observation": "<pr_description>Fix BlockDelimiters</pr_description>",
                "done": False,
                "truncated": False,
            },
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_step",
            lambda **kwargs: {
                "episode_id": "ep-1",
                "observation": "<returncode>0</returncode><output>noop</output>",
                "done": False,
                "truncated": False,
            },
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "state", "info": {"changed_files": []}},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_restore",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "restored baseline"},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )

        def fake_chat_completion(**kwargs):
            prompts.append(kwargs["messages"])
            return {"choices": [{"message": {"content": next(responses)}}]}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis._chat_completion", fake_chat_completion)

        run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="teacher-model",
            api_key="token",
            max_steps=2,
            max_root_retries=1,
            max_edit_retries=0,
        )

        assert len(prompts) == 2
        assert prompts[1][1]["content"] == prompts[0][1]["content"]
        assert all(
            "Avoid repeating these no-progress commands" not in message["content"]
            for prompt in prompts
            for message in prompt
        )

    def test_synthesis_keeps_successful_search_observation_without_restore(self, monkeypatch, tmp_path):
        calls: list[str] = []
        responses = iter(["```bash\ncd /app && git grep -n \"BlockDelimiters\"\n```", "```bash\n<submit-placeholder>\n```"])

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {
                "episode_id": "ep-1",
                "observation": "<pr_description>Fix BlockDelimiters</pr_description>",
                "done": False,
                "truncated": False,
            },
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"},
        )

        def fake_step(**kwargs):
            calls.append(kwargs["action_text"])
            if "git grep" in kwargs["action_text"]:
                return {
                    "episode_id": "ep-1",
                    "observation": "<returncode>0</returncode>\n<output>\nlib/rubocop/cop/style/block_delimiters.rb:1:test\n</output>",
                    "done": False,
                    "truncated": False,
                }
            return {"episode_id": "ep-1", "observation": "done", "done": True, "truncated": False}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_step", fake_step)
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "state", "info": {"changed_files": []}},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_restore",
            lambda **kwargs: (_ for _ in ()).throw(AssertionError("restore should not be called after successful search")),
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._chat_completion",
            lambda **kwargs: {"choices": [{"message": {"content": next(responses)}}]},
        )

        run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="teacher-model",
            api_key="token",
            max_steps=2,
            max_root_retries=1,
            max_edit_retries=0,
        )

        assert any("git grep -n" in action for action in calls)

    def test_synthesis_keeps_search_output_even_when_shell_returncode_is_nonzero(self, monkeypatch, tmp_path):
        restores: list[dict] = []
        responses = iter(
            [
                "```bash\ncd /app && git grep -n \"BlockDelimiters\" && git grep -n \"RequiredBracesMethods\"\n```",
                "```bash\ncd /app && sed -n '1,40p' lib/rubocop/cop/style/block_delimiters.rb\n```",
            ]
        )

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {
                "episode_id": "ep-1",
                "observation": "<pr_description>Fix BlockDelimiters</pr_description>",
                "done": False,
                "truncated": False,
            },
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"},
        )

        def fake_step(**kwargs):
            if "git grep -n" in kwargs["action_text"]:
                return {
                    "episode_id": "ep-1",
                    "observation": "<returncode>1</returncode>\n<output>\nlib/rubocop/cop/style/block_delimiters.rb:1:test\n</output>",
                    "done": False,
                    "truncated": False,
                }
            return {"episode_id": "ep-1", "observation": "done", "done": True, "truncated": False}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_step", fake_step)
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "state", "info": {"changed_files": []}},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_restore",
            lambda **kwargs: restores.append(kwargs) or {"episode_id": "ep-1", "observation": "restored baseline"},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._chat_completion",
            lambda **kwargs: {"choices": [{"message": {"content": next(responses)}}]},
        )

        run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="teacher-model",
            api_key="token",
            max_steps=2,
            max_root_retries=1,
            max_edit_retries=0,
        )

        assert restores == []

    def test_synthesis_enables_student_thinking_only_for_student_calls(self, monkeypatch, tmp_path):
        captured_enable_thinking: list[bool] = []

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "prompt", "done": False, "truncated": False},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_step",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "done", "done": True, "truncated": False},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "state", "info": {"changed_files": []}},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )

        def fake_chat_completion(**kwargs):
            captured_enable_thinking.append(bool(kwargs.get("enable_thinking")))
            return {"output_text": "```bash\ncd /app && git grep -n \"needle\"\n```"}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis._chat_completion", fake_chat_completion)

        run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="student-model",
            api_key="token",
            student_enable_thinking=True,
            max_steps=1,
        )

        assert captured_enable_thinking == [True]

    def test_synthesis_injects_teacher_think_after_no_progress(self, monkeypatch, tmp_path):
        prompts: list[list[dict[str, str]]] = []
        responses = iter(
            [
                "```bash\ncd /app && git log --oneline -20\n```",
                "```bash\ncd /app && git grep -n \"fromVersion\" release_notes.py\n```",
            ]
        )

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {
                "episode_id": "ep-1",
                "observation": "<pr_description>Fix release notes generator</pr_description>",
                "done": False,
                "truncated": False,
            },
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_step",
            lambda **kwargs: {
                "episode_id": "ep-1",
                "observation": "<returncode>0</returncode><output>noop</output>",
                "done": False,
                "truncated": False,
            },
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "state", "info": {"changed_files": []}},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_restore",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "restored baseline"},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )

        decisions = iter(
            [
                ({"branch_decision": "CURRENT", "inject_teacher_think": False, "teacher_think_text": "", "reason": "initial current"}, {"output_text": "{}"}, "{}"),
                (
                    {
                        "branch_decision": "CURRENT",
                        "inject_teacher_think": True,
                        "teacher_think_text": "Inspect release_notes.py and then edit the exact fromVersion fallback.",
                        "reason": "student stalled on git log",
                    },
                    {"output_text": "{\"branch_decision\":\"CURRENT\",\"inject_teacher_think\":true,\"teacher_think_text\":\"Inspect release_notes.py and then edit the exact fromVersion fallback.\",\"reason\":\"student stalled on git log\"}"},
                    "{\"branch_decision\":\"CURRENT\",\"inject_teacher_think\":true,\"teacher_think_text\":\"Inspect release_notes.py and then edit the exact fromVersion fallback.\",\"reason\":\"student stalled on git log\"}",
                ),
            ]
        )

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._teacher_controller_decision",
            lambda **kwargs: next(decisions),
        )

        def fake_chat_completion(**kwargs):
            prompts.append(kwargs["messages"])
            return {"output_text": next(responses)}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis._chat_completion", fake_chat_completion)

        result = run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="student-model",
            api_key="token",
            teacher_model="teacher-model",
            inject_teacher_think=True,
            max_steps=2,
            max_root_retries=1,
        )

        think_prompts = [
            prompt
            for prompt in prompts[1:]
            if any("<teacher_guidance>" in message["content"] for message in prompt)
        ]
        assert think_prompts
        assert all([message["role"] for message in prompt][-2:] != ["user", "user"] for prompt in think_prompts)
        assert any(
            "<teacher_guidance>" in prompt[-1]["content"] and "Use the following hidden guidance for your next THOUGHT only." in prompt[-1]["content"]
            for prompt in think_prompts
        )
        assert result["teacher_think_calls"] == 1
        events = (tmp_path / "synth" / "raw" / "synthesis_events.jsonl").read_text().splitlines()
        teacher_think_events = [json.loads(line) for line in events if json.loads(line).get("kind") == "teacher_think"]
        assert teacher_think_events
        assert teacher_think_events[0]["text"] == "Inspect release_notes.py and then edit the exact fromVersion fallback."
        assert teacher_think_events[0]["think_text"] == teacher_think_events[0]["text"]

    def test_teacher_controller_decision_falls_back_on_invalid_json(self, monkeypatch):
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._chat_completion",
            lambda **kwargs: {"output_text": "not-json"},
        )

        decision, payload, raw = synthesis_module._teacher_controller_decision(
            api_base="https://example.invalid/v1",
            api_key="token",
            model="teacher-model",
            controller_context={"task_id": "1", "student_messages": []},
            reasoning_effort="low",
            timeout=30,
        )

        assert payload["output_text"] == "not-json"
        assert raw == "not-json"
        assert decision["branch_decision"] == "CURRENT"
        assert decision["inject_teacher_think"] is False
        assert decision["teacher_think_text"] == ""
        assert "structured_parse_fallback" in decision["reason"]

    def test_resolve_teacher_api_base_prefers_openai_base_url_env_for_teacher(self, monkeypatch):
        monkeypatch.setenv("OPENAI_BASE_URL", "https://api.aicodemirror.com/api/codex/backend-api/codex/v1")
        resolved = synthesis_module._resolve_teacher_api_base(
            student_api_base="http://127.0.0.1:30001/v1",
            teacher_api_base="",
            teacher_model="gpt-5.4",
            teacher_api_key="sk-test",
            teacher_api_key_file="",
        )
        assert resolved == "https://api.aicodemirror.com/api/codex/backend-api/codex/v1"

    def test_resolve_teacher_api_base_prefers_explicit_teacher_base(self, monkeypatch):
        monkeypatch.setenv("OPENAI_BASE_URL", "https://api.aicodemirror.com/api/codex/backend-api/codex/v1")
        resolved = synthesis_module._resolve_teacher_api_base(
            student_api_base="http://127.0.0.1:30001/v1",
            teacher_api_base="https://explicit.teacher.example/v1",
            teacher_model="gpt-5.4",
            teacher_api_key="sk-test",
            teacher_api_key_file="",
        )
        assert resolved == "https://explicit.teacher.example/v1"

    def test_chat_completion_falls_back_to_sglang_generate(self, monkeypatch):
        class FakeExc(Exception):
            def __init__(self, message: str, status_code: int | None = None):
                super().__init__(message)
                self.status_code = status_code

        class FakeResponses:
            def create(self, **kwargs):
                raise FakeExc("Not Found", 404)

        class FakeChatCompletions:
            def create(self, **kwargs):
                raise FakeExc("input_ids should be a list of lists for batch processing.", 400)

        class FakeChat:
            completions = FakeChatCompletions()

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.responses = FakeResponses()
                self.chat = FakeChat()

        monkeypatch.setattr(synthesis_module, "OpenAI", FakeOpenAI)
        monkeypatch.setattr(
            synthesis_module,
            "_sglang_generate_completion",
            lambda **kwargs: {"id": "gen-1", "model": kwargs["model"], "output_text": "```bash\necho hello\n```", "transport": "sglang_generate"},
        )

        payload = synthesis_module._chat_completion(
            api_base="http://127.0.0.1:30001/v1",
            api_key="dummy",
            model="fakemoonlo/Affine-5FnfLT3ntQXDsAnVC5H5WNQYVTY7SSCbxU3kxqhNybtJeNGb",
            messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}],
            temperature=0.0,
            reasoning_effort="low",
            timeout=30,
            enable_thinking=True,
        )

        assert payload["transport"] == "sglang_generate"
        assert payload["output_text"] == "```bash\necho hello\n```"

    def test_chat_completion_passes_student_max_new_tokens_to_sglang_generate(self, monkeypatch):
        captured: dict[str, object] = {}

        class FakeExc(Exception):
            def __init__(self, message: str, status_code: int | None = None):
                super().__init__(message)
                self.status_code = status_code

        class FakeResponses:
            def create(self, **kwargs):
                raise FakeExc("Not Found", 404)

        class FakeChatCompletions:
            def create(self, **kwargs):
                raise FakeExc("input_ids should be a list of lists for batch processing.", 400)

        class FakeChat:
            completions = FakeChatCompletions()

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.responses = FakeResponses()
                self.chat = FakeChat()

        monkeypatch.setattr(synthesis_module, "OpenAI", FakeOpenAI)

        def fake_generate(**kwargs):
            captured.update(kwargs)
            return {"id": "gen-1", "model": kwargs["model"], "output_text": "```bash\necho hello\n```", "transport": "sglang_generate"}

        monkeypatch.setattr(synthesis_module, "_sglang_generate_completion", fake_generate)

        synthesis_module._chat_completion(
            api_base="http://127.0.0.1:30001/v1",
            api_key="dummy",
            model="fakemoonlo/Affine-5FnfLT3ntQXDsAnVC5H5WNQYVTY7SSCbxU3kxqhNybtJeNGb",
            messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}],
            temperature=0.0,
            reasoning_effort="low",
            timeout=30,
            enable_thinking=True,
            student_max_new_tokens=4096,
        )

        assert captured["max_new_tokens"] == 4096

    def test_chat_completion_falls_back_to_sglang_generate_on_responses_400(self, monkeypatch):
        captured: dict[str, object] = {}
        calls: list[str] = []

        class FakeExc(Exception):
            def __init__(self, message: str, status_code: int | None = None):
                super().__init__(message)
                self.status_code = status_code

        class FakeResponses:
            def create(self, **kwargs):
                calls.append("responses")
                raise FakeExc("input_ids should be a list of lists for batch processing.", 400)

        class FakeChatCompletions:
            def create(self, **kwargs):
                calls.append("chat")
                raise FakeExc("input_ids should be a list of lists for batch processing.", 400)

        class FakeChat:
            completions = FakeChatCompletions()

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.responses = FakeResponses()
                self.chat = FakeChat()

        monkeypatch.setattr(synthesis_module, "OpenAI", FakeOpenAI)

        def fake_generate(**kwargs):
            captured.update(kwargs)
            return {
                "id": "gen-400",
                "model": kwargs["model"],
                "output_text": "```bash\necho hello\n```",
                "transport": "sglang_generate",
            }

        monkeypatch.setattr(synthesis_module, "_sglang_generate_completion", fake_generate)

        payload = synthesis_module._chat_completion(
            api_base="http://127.0.0.1:30001/v1",
            api_key="dummy",
            model="Qwen/Qwen3.6-35B-A3B",
            messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}],
            temperature=0.0,
            reasoning_effort="low",
            timeout=30,
            enable_thinking=False,
            student_max_new_tokens=2048,
        )

        assert payload["transport"] == "sglang_generate"
        assert captured["max_new_tokens"] == 2048
        assert calls == ["chat"]

    def test_chat_completion_prefers_chat_completions_first_for_local_qwen(self, monkeypatch):
        calls: list[str] = []

        class FakeExc(Exception):
            def __init__(self, message: str, status_code: int | None = None):
                super().__init__(message)
                self.status_code = status_code

        class FakeResponses:
            def create(self, **kwargs):
                calls.append("responses")
                raise FakeExc("input_ids should be a list of lists for batch processing.", 400)

        class FakeChoice:
            def model_dump(self, mode="json"):
                return {"message": {"content": "```bash\necho hello\n```"}}

        class FakeChatCompletions:
            def create(self, **kwargs):
                calls.append("chat")
                return type("Resp", (), {"id": "chat-id", "model": kwargs["model"], "choices": [FakeChoice()]})()

        class FakeChat:
            completions = FakeChatCompletions()

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.responses = FakeResponses()
                self.chat = FakeChat()

        monkeypatch.setattr(synthesis_module, "OpenAI", FakeOpenAI)

        payload = synthesis_module._chat_completion(
            api_base="http://127.0.0.1:30001/v1",
            api_key="dummy",
            model="Qwen/Qwen3.6-35B-A3B",
            messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}],
            temperature=0.0,
            reasoning_effort="low",
            timeout=30,
            enable_thinking=False,
            student_max_new_tokens=2048,
        )

        assert calls == ["chat"]
        assert payload["id"] == "chat-id"

    def test_chat_completion_retries_local_qwen_without_think_on_reasoning_only_response(self, monkeypatch):
        calls: list[dict[str, object]] = []

        class FakeChoice:
            def __init__(self, message: dict[str, object]):
                self._message = message

            def model_dump(self, mode="json"):
                return {"message": self._message}

        class FakeChatCompletions:
            def __init__(self):
                self._count = 0

            def create(self, **kwargs):
                self._count += 1
                calls.append(kwargs)
                if self._count == 1:
                    return type(
                        "Resp",
                        (),
                        {
                            "id": "chat-id-1",
                            "model": kwargs["model"],
                            "choices": [FakeChoice({"content": None, "reasoning_content": "hidden reasoning"})],
                        },
                    )()
                return type(
                    "Resp",
                    (),
                    {
                        "id": "chat-id-2",
                        "model": kwargs["model"],
                        "choices": [FakeChoice({"content": "```bash\necho hello\n```"})],
                    },
                )()

        class FakeChat:
            def __init__(self):
                self.completions = FakeChatCompletions()

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.responses = type("Resp", (), {"create": lambda self, **kwargs: None})()
                self.chat = FakeChat()

        monkeypatch.setattr(synthesis_module, "OpenAI", FakeOpenAI)

        payload = synthesis_module._chat_completion(
            api_base="http://127.0.0.1:30001/v1",
            api_key="dummy",
            model="Qwen/Qwen3.5-27B-FP8",
            messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}],
            temperature=0.0,
            reasoning_effort="low",
            timeout=30,
            enable_thinking=True,
            retry_without_think_on_no_text=True,
        )

        assert len(calls) == 2
        assert calls[0]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": True}}
        assert calls[1]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
        assert payload["student_retry_without_think"] is True
        assert payload["student_response_attempt"] == 2
        assert synthesis_module._extract_text(payload) == "```bash\necho hello\n```"

    def test_chat_completion_promotes_local_fakemoon_reasoning_content_without_retry(self, monkeypatch):
        calls: list[dict[str, object]] = []

        class FakeChoice:
            def __init__(self, message: dict[str, object]):
                self._message = message

            def model_dump(self, mode="json"):
                return {"message": self._message}

        class FakeChatCompletions:
            def __init__(self):
                self._count = 0

            def create(self, **kwargs):
                self._count += 1
                calls.append(kwargs)
                if self._count == 1:
                    return type(
                        "Resp",
                        (),
                        {
                            "id": "chat-id-1",
                            "model": kwargs["model"],
                            "choices": [FakeChoice({"content": None, "reasoning_content": "hidden reasoning"})],
                        },
                    )()
                return type(
                    "Resp",
                    (),
                    {
                        "id": "chat-id-2",
                        "model": kwargs["model"],
                        "choices": [FakeChoice({"content": "```bash\necho hello\n```"})],
                    },
                )()

        class FakeChat:
            def __init__(self):
                self.completions = FakeChatCompletions()

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.responses = type("Resp", (), {"create": lambda self, **kwargs: None})()
                self.chat = FakeChat()

        monkeypatch.setattr(synthesis_module, "OpenAI", FakeOpenAI)

        payload = synthesis_module._chat_completion(
            api_base="http://127.0.0.1:30001/v1",
            api_key="dummy",
            model="fakemoonlo/Affine-5FnfLT3ntQXDsAnVC5H5WNQYVTY7SSCbxU3kxqhNybtJeNGb",
            messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}],
            temperature=0.0,
            reasoning_effort="low",
            timeout=30,
            enable_thinking=True,
            retry_without_think_on_no_text=True,
        )

        assert len(calls) == 1
        assert calls[0]["extra_body"] == {"enable_thinking": True}
        assert payload["student_retry_without_think"] is False
        assert payload["student_response_attempt"] == 1
        assert synthesis_module._extract_text(payload) == "hidden reasoning"

    def test_chat_completion_promotes_fakemoon_reasoning_content_to_content(self, monkeypatch):
        calls: list[dict[str, object]] = []

        class FakeChoice:
            def model_dump(self, mode="json"):
                return {
                    "message": {
                        "content": None,
                        "reasoning_content": "THOUGHT: inspect\n\n```bash\nls -la\n```",
                    }
                }

        class FakeChatCompletions:
            def create(self, **kwargs):
                calls.append(kwargs)
                return type(
                    "Resp",
                    (),
                    {
                        "id": "chat-id-1",
                        "model": kwargs["model"],
                        "choices": [FakeChoice()],
                    },
                )()

        class FakeChat:
            def __init__(self):
                self.completions = FakeChatCompletions()

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.responses = type("Resp", (), {"create": lambda self, **kwargs: None})()
                self.chat = FakeChat()

        monkeypatch.setattr(synthesis_module, "OpenAI", FakeOpenAI)

        payload = synthesis_module._chat_completion(
            api_base="http://127.0.0.1:30001/v1",
            api_key="dummy",
            model="fakemoonlo/Affine-5FnfLT3ntQXDsAnVC5H5WNQYVTY7SSCbxU3kxqhNybtJeNGb",
            messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}],
            temperature=0.0,
            reasoning_effort="low",
            timeout=30,
            enable_thinking=True,
            retry_without_think_on_no_text=True,
        )

        assert len(calls) == 1
        assert payload["student_retry_without_think"] is False
        assert payload["student_response_attempt"] == 1
        assert synthesis_module._extract_text(payload) == "THOUGHT: inspect\n\n```bash\nls -la\n```"

    def test_chat_completion_raises_when_local_qwen_retry_still_has_no_content(self, monkeypatch):
        class FakeChoice:
            def __init__(self, message: dict[str, object]):
                self._message = message

            def model_dump(self, mode="json"):
                return {"message": self._message}

        class FakeChatCompletions:
            def create(self, **kwargs):
                return type(
                    "Resp",
                    (),
                    {
                        "id": "chat-id",
                        "model": kwargs["model"],
                        "choices": [FakeChoice({"content": None, "reasoning_content": "hidden reasoning"})],
                    },
                )()

        class FakeChat:
            def __init__(self):
                self.completions = FakeChatCompletions()

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.responses = type("Resp", (), {"create": lambda self, **kwargs: None})()
                self.chat = FakeChat()

        monkeypatch.setattr(synthesis_module, "OpenAI", FakeOpenAI)

        with pytest.raises(RuntimeError, match="no text content after no-think retry"):
            synthesis_module._chat_completion(
                api_base="http://127.0.0.1:30001/v1",
                api_key="dummy",
                model="Qwen/Qwen3.5-27B-FP8",
                messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}],
                temperature=0.0,
                reasoning_effort="low",
                timeout=30,
                enable_thinking=True,
                retry_without_think_on_no_text=True,
            )

    def test_synthesis_eval_mode_stops_on_context_limit(self, monkeypatch, tmp_path):
        student_calls = {"value": 0}

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "prompt", "done": False, "truncated": False},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_step",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "still going", "done": False, "truncated": False},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "state", "info": {"changed_files": [], "last_patch_hash": ""}},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )
        counts = iter([128, 40000])
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._count_rendered_prompt_tokens",
            lambda **kwargs: next(counts),
        )

        def fake_chat_completion(**kwargs):
            student_calls["value"] += 1
            return {"output_text": "```bash\ncd /app && ls -la\n```"}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis._chat_completion", fake_chat_completion)

        result = run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="student-model",
            api_key="token",
            max_steps=10,
            eval_mode=True,
            eval_max_context_tokens=32768,
        )

        assert student_calls["value"] == 1
        assert result["terminal_status"] == "context_limit"
        assert result["final_context_tokens"] == 40000
        assert result["teacher_calls"] == 0

    def test_synthesis_eval_mode_stops_on_model_stop(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "prompt", "done": False, "truncated": False},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._count_rendered_prompt_tokens",
            lambda **kwargs: 64,
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._chat_completion",
            lambda **kwargs: {"output_text": "I will stop here."},
        )

        result = run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="student-model",
            api_key="token",
            max_steps=10,
            eval_mode=True,
        )

        assert result["terminal_status"] == "model_stop"
        assert result["student_calls"] == 1
        assert result["final_done"] is False
        assert result["model_stop_reason"] == "no_executable_action"

    def test_synthesis_eval_mode_marks_generation_truncation(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "prompt", "done": False, "truncated": False},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._count_rendered_prompt_tokens",
            lambda **kwargs: 64,
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._chat_completion",
            lambda **kwargs: {
                "output_text": "THOUGHT: partial",
                "transport": "sglang_generate",
                "meta_info": {"finish_reason": {"type": "length", "length": 1024}},
            },
        )

        result = run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="student-model",
            api_key="token",
            max_steps=10,
            eval_mode=True,
            student_max_new_tokens=4096,
        )

        assert result["terminal_status"] == "model_stop"
        assert result["model_stop_reason"] == "generation_truncated"
        assert result["student_transport"] == "sglang_generate"
        assert result["student_finish_reason_type"] == "length"
        assert result["student_finish_reason_length"] == 1024

    def test_synthesis_eval_mode_retries_transport_once(self, monkeypatch, tmp_path):
        calls = {"value": 0}

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "prompt", "done": False, "truncated": False},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_step",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "done", "done": True, "truncated": False, "reward": 0.0, "info": {"test_stats": {}}},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "state", "info": {"changed_files": [], "last_patch_hash": ""}},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._count_rendered_prompt_tokens",
            lambda **kwargs: 64,
        )

        def fake_chat_completion(**kwargs):
            calls["value"] += 1
            if calls["value"] == 1:
                raise RuntimeError("chat.completions.create failed: Request timed out.")
            return {"output_text": "```bash\necho ok\n```"}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis._chat_completion", fake_chat_completion)

        result = run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="student-model",
            api_key="token",
            max_steps=2,
            eval_mode=True,
            transport_only_retries=1,
        )

        assert calls["value"] == 2
        assert result["transport_retries_used"] == 1
        assert result["terminal_status"] == "done"

    def test_synthesis_waits_for_rollout_release_before_first_model_action(self, monkeypatch, tmp_path):
        ready_file = tmp_path / "ready.json"
        release_file = tmp_path / "release.json"
        worker = {"started": False}

        monkeypatch.setenv("ORBIT_SWE_PAUSE_BEFORE_FIRST_MODEL_ACTION", "true")
        monkeypatch.setenv("ORBIT_SWE_BOOTSTRAP_READY_FILE", str(ready_file))
        monkeypatch.setenv("ORBIT_SWE_ROLLOUT_RELEASE_FILE", str(release_file))
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "prompt", "done": False, "truncated": False},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_step",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "done", "done": True, "truncated": False, "reward": 0.0, "info": {"test_stats": {}}},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "state", "info": {"changed_files": [], "last_patch_hash": ""}},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )

        def fake_chat_completion(**kwargs):
            assert release_file.exists()
            return {"output_text": "```bash\necho ok\n```"}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis._chat_completion", fake_chat_completion)

        def release_worker():
            worker["started"] = True
            deadline = time.time() + 20
            while time.time() < deadline:
                if ready_file.exists():
                    release_file.write_text("go\n", encoding="utf-8")
                    return
                time.sleep(0.05)
            raise AssertionError("ready file was not written")

        thread = threading.Thread(target=release_worker, daemon=True)
        thread.start()
        result = run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="student-model",
            api_key="token",
            max_steps=1,
            eval_mode=True,
        )
        thread.join(timeout=5)

        events = (tmp_path / "synth" / "raw" / "synthesis_events.jsonl").read_text(encoding="utf-8")
        assert worker["started"] is True
        assert thread.is_alive() is False
        assert ready_file.exists()
        assert release_file.exists()
        assert "\"kind\": \"bootstrap_ready\"" in events
        assert "\"kind\": \"bootstrap_release\"" in events
        assert result["terminal_status"] == "done"

    def test_synthesis_writes_manifest_on_runtime_bootstrap_failure(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: (_ for _ in ()).throw(RuntimeError("/tmp/run/.runtime/venv/bin/python: No module named pip")),
        )

        result = run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="student-model",
            api_key="token",
            max_steps=2,
            eval_mode=True,
        )

        manifest = json.loads((tmp_path / "synth" / "manifests" / "synthesis_run.json").read_text(encoding="utf-8"))
        events = (tmp_path / "synth" / "raw" / "synthesis_events.jsonl").read_text(encoding="utf-8")
        assert result["terminal_status"] == "runtime_bootstrap_failed"
        assert manifest["terminal_status"] == "runtime_bootstrap_failed"
        assert manifest["failure_reason"] == "runtime_bootstrap_failed"
        assert "\"kind\": \"fatal_error\"" in events

    def test_synthesis_eval_mode_does_not_rewrite_or_reject_actions(self, monkeypatch, tmp_path):
        observed_actions: list[str] = []

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "prompt", "done": False, "truncated": False},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_step",
            lambda **kwargs: observed_actions.append(kwargs["action_text"]) or {
                "episode_id": "ep-1",
                "observation": "done",
                "done": True,
                "truncated": False,
                "reward": 0.0,
                "info": {"test_stats": {}},
            },
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "state", "info": {"changed_files": [], "last_patch_hash": ""}},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._chat_completion",
            lambda **kwargs: {"output_text": "```bash\npython - <<'PY'\nprint(1)\nPY\n```"},
        )

        result = run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="student-model",
            api_key="token",
            max_steps=2,
            eval_mode=True,
        )

        assert observed_actions == ["```bash\npython - <<'PY'\nprint(1)\nPY\n```"]
        assert result["final_done"] is True

    def test_synthesis_eval_mode_ignores_teacher_and_restore_logic(self, monkeypatch, tmp_path):
        teacher_called = {"value": 0}
        restores: list[dict[str, object]] = []
        stop_calls = {"value": 0}

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "prompt", "done": False, "truncated": False},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_step",
            lambda **kwargs: {
                "episode_id": "ep-1",
                "observation": "done",
                "done": True,
                "truncated": False,
                "reward": 0.0,
                "info": {"test_stats": {}},
            },
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "state", "info": {"changed_files": ["target.txt"], "last_patch_hash": "patch-1"}},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_restore",
            lambda **kwargs: restores.append(kwargs) or {"episode_id": "ep-1", "observation": "restored"},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: stop_calls.__setitem__("value", stop_calls["value"] + 1) or {"episode_id": "ep-1", "stopped": True},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._teacher_controller_decision",
            lambda **kwargs: teacher_called.__setitem__("value", teacher_called["value"] + 1) or (_ for _ in ()).throw(AssertionError("teacher should not be called in clean eval")),
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._chat_completion",
            lambda **kwargs: {"output_text": "```bash\ncd /app && sed -i 's/old/new/' target.txt\n```"},
        )

        result = run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="student-model",
            api_key="token",
            teacher_model="teacher-model",
            teacher_api_base="https://example.invalid/v1",
            teacher_api_key="token",
            max_steps=2,
            eval_mode=True,
            eval_max_context_tokens=65536,
        )

        assert teacher_called["value"] == 0
        assert restores == []
        assert stop_calls["value"] == 1
        assert result["clean_eval"] is True
        assert result["teacher_calls"] == 0
        assert result["teacher_branch_calls"] == 0
        assert result["teacher_think_calls"] == 0
        assert result["restore_budget_used"] == 0
        assert result["checkpoint_ring_depth"] == 0
        assert result["restore_target_applied"] == "CURRENT"
        events = (tmp_path / "synth" / "raw" / "synthesis_events.jsonl").read_text().splitlines()
        kinds = [json.loads(line).get("kind") for line in events]
        assert "teacher_decision" not in kinds
        assert "teacher_branch" not in kinds
        assert "teacher_think" not in kinds
        assert "restore" not in kinds
        assert "control_stop" not in kinds

    def test_synthesis_after_file_view_prompts_for_edit(self, monkeypatch, tmp_path):
        prompts: list[list[dict[str, str]]] = []
        responses = iter(
            [
                "```bash\ncd /app && sed -n '1,40p' lib/rubocop/cop/style/block_delimiters.rb\n```",
                "```bash\ncd /app && python - <<'PY'\nfrom pathlib import Path\np = Path('lib/rubocop/cop/style/block_delimiters.rb')\ntext = p.read_text()\np.write_text(text)\nPY\n```",
            ]
        )

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {
                "episode_id": "ep-1",
                "observation": "<pr_description>Fix BlockDelimiters</pr_description>",
                "done": False,
                "truncated": False,
            },
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"},
        )

        def fake_step(**kwargs):
            if "sed -n" in kwargs["action_text"]:
                return {
                    "episode_id": "ep-1",
                    "observation": "<returncode>0</returncode>\n<output>\n# frozen_string_literal: true\nclass BlockDelimiters\n</output>",
                    "done": False,
                    "truncated": False,
                }
            return {"episode_id": "ep-1", "observation": "done", "done": True, "truncated": False}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_step", fake_step)
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "state", "info": {"changed_files": []}},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )

        def fake_chat_completion(**kwargs):
            prompts.append(kwargs["messages"])
            return {"choices": [{"message": {"content": next(responses)}}]}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis._chat_completion", fake_chat_completion)

        run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="teacher-model",
            api_key="token",
            max_steps=2,
            max_root_retries=0,
            max_edit_retries=0,
        )

        assert len(prompts) == 2
        assert any(
            "# frozen_string_literal: true" in message["content"]
            for message in prompts[1]
            if isinstance(message.get("content"), str)
        )
        assert all(
            "must make one minimal non-interactive edit" not in message["content"]
            for prompt in prompts
            for message in prompt
            if isinstance(message.get("content"), str)
        )

    def test_synthesis_after_failed_edit_stays_on_same_file_and_avoids_restore(self, monkeypatch, tmp_path):
        prompts: list[list[dict[str, str]]] = []
        restores: list[dict] = []
        responses = iter(
            [
                "```bash\ncd /app && sed -n '1,40p' lib/rubocop/cop/style/block_delimiters.rb\n```",
                "```bash\npython - <<'PY'\nprint('edit')\nPY\n```",
                "```bash\nruby -e 'print :ok'\n```",
                "```bash\ncd /app && sed -n '1,40p' lib/rubocop/cop/style/block_delimiters.rb\n```",
            ]
        )

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {
                "episode_id": "ep-1",
                "observation": "<pr_description>Fix BlockDelimiters</pr_description>",
                "done": False,
                "truncated": False,
            },
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"},
        )

        step_counter = {"value": 0}

        def fake_step(**kwargs):
            step_counter["value"] += 1
            if step_counter["value"] == 1:
                return {
                    "episode_id": "ep-1",
                    "observation": "<returncode>0</returncode>\n<output>\n# frozen_string_literal: true\nclass BlockDelimiters\n</output>",
                    "done": False,
                    "truncated": False,
                }
            if step_counter["value"] == 2:
                return {
                    "episode_id": "ep-1",
                    "observation": "<returncode>127</returncode>\n<output>\nbash: line 1: python: command not found\n</output>",
                    "done": False,
                    "truncated": False,
                }
            return {"episode_id": "ep-1", "observation": "done", "done": True, "truncated": False}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_step", fake_step)
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "state", "info": {"changed_files": []}},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_restore",
            lambda **kwargs: restores.append(kwargs) or {"episode_id": "ep-1", "observation": "restored baseline"},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )

        def fake_chat_completion(**kwargs):
            prompts.append(kwargs["messages"])
            return {"choices": [{"message": {"content": next(responses)}}]}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis._chat_completion", fake_chat_completion)

        run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="teacher-model",
            api_key="token",
            max_steps=3,
            max_root_retries=1,
            max_edit_retries=0,
        )

        assert restores == [{"output_dir": str(tmp_path / "synth"), "episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"}]
        assert all(
            "Do not search again" not in message["content"]
            for prompt in prompts
            for message in prompt
            if isinstance(message.get("content"), str)
        )

    def test_synthesis_rewrites_python_to_python3_when_preferred(self, monkeypatch, tmp_path):
        observed_actions: list[str] = []
        responses = iter(
            [
                "```bash\ncd /app && sed -n '1,40p' release_notes.py\n```",
                "```bash\npython - <<'PY'\nprint('edit')\nPY\n```",
            ]
        )

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {
                "episode_id": "ep-1",
                "observation": "<pr_description>fix release notes generator</pr_description>",
                "done": False,
                "truncated": False,
            },
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"},
        )

        def fake_step(**kwargs):
            observed_actions.append(kwargs["action_text"])
            if len(observed_actions) == 1:
                return {
                    "episode_id": "ep-1",
                    "observation": "<returncode>0</returncode>\n<output>\nfrom_version = cnt.get(\"fromversion\")\n</output>",
                    "done": False,
                    "truncated": False,
                }
            return {"episode_id": "ep-1", "observation": "done", "done": True, "truncated": False}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_step", fake_step)
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "state", "info": {"changed_files": []}},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._chat_completion",
            lambda **kwargs: {"choices": [{"message": {"content": next(responses)}}]},
        )

        run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="teacher-model",
            api_key="token",
            max_steps=2,
            max_root_retries=0,
            max_edit_retries=0,
        )

        assert any("python3 - <<'PY'" in action for action in observed_actions)

    def test_synthesis_restores_edited_checkpoint_after_repeated_verify_with_same_patch(self, monkeypatch, tmp_path):
        restores: list[dict] = []
        responses = iter(
            [
                "```bash\ncd /app && sed -n '1,40p' release_notes.py\n```",
                "```bash\npython - <<'PY'\nfrom pathlib import Path\np = Path('release_notes.py')\ns = p.read_text()\np.write_text(s + '\\n# edit\\n')\nPY\n```",
                "```bash\npython -m py_compile release_notes.py\n```",
                "```bash\ncd /app && git diff -- release_notes.py\n```",
                "```bash\ncd /app && git diff -- release_notes.py\n```",
                "```bash\ncd /app && git diff -- release_notes.py\n```",
            ]
        )

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {
                "episode_id": "ep-1",
                "observation": "<pr_description>fix release notes generator</pr_description>",
                "done": False,
                "truncated": False,
            },
        )

        def fake_checkpoint(**kwargs):
            label = kwargs.get("label") or "baseline"
            return {"episode_id": "ep-1", "checkpoint_id": f"{label}-ckpt"}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint", fake_checkpoint)

        step_counter = {"value": 0}

        def fake_step(**kwargs):
            step_counter["value"] += 1
            if step_counter["value"] == 1:
                return {
                    "episode_id": "ep-1",
                    "observation": "<returncode>0</returncode>\n<output>\n1\tfrom_version = cnt.get(\"fromversion\")\n</output>",
                    "done": False,
                    "truncated": False,
                }
            if step_counter["value"] == 2:
                return {
                    "episode_id": "ep-1",
                    "observation": "<returncode>0</returncode>\n<output>\ndiff --git a/release_notes.py b/release_notes.py\n</output>",
                    "done": False,
                    "truncated": False,
                }
            return {
                "episode_id": "ep-1",
                "observation": "<returncode>0</returncode>\n<output>\n</output>",
                "done": False,
                "truncated": False,
            }

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_step", fake_step)

        state_counter = {"value": 0}

        def fake_state(**kwargs):
            state_counter["value"] += 1
            if state_counter["value"] == 1:
                return {"episode_id": "ep-1", "observation": "state", "info": {"changed_files": [], "last_patch_hash": ""}}
            return {
                "episode_id": "ep-1",
                "observation": "state",
                "info": {"changed_files": ["release_notes.py"], "last_patch_hash": "patch-1"},
            }

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_state", fake_state)
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_restore",
            lambda **kwargs: restores.append(kwargs) or {"episode_id": "ep-1", "observation": "restored edit"},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._chat_completion",
            lambda **kwargs: {"choices": [{"message": {"content": next(responses)}}]},
        )

        run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="teacher-model",
            api_key="token",
            max_steps=6,
            max_root_retries=0,
            max_edit_retries=1,
        )

        assert restores == [{"output_dir": str(tmp_path / "synth"), "episode_id": "ep-1", "checkpoint_id": "post-edit-2-ckpt"}]

    def test_synthesis_keeps_student_prompt_path_without_teacher_action_takeover(self, monkeypatch, tmp_path):
        used_models: list[str] = []
        responses = {
            "student-model": iter(
                [
                    "```bash\ncd /app && git grep -n \"BlockDelimiters\" lib spec\n```",
                    "```bash\ncd /app && sed -n '1,40p' lib/rubocop/cop/style/block_delimiters.rb\n```",
                    "```bash\ncd /app && git grep -n \"line_count_based\" lib spec\n```",
                ]
            ),
        }

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {
                "episode_id": "ep-1",
                "observation": "<pr_description>Fix BlockDelimiters</pr_description>",
                "done": False,
                "truncated": False,
            },
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {"episode_id": "ep-1", "checkpoint_id": "baseline-ckpt"},
        )

        step_counter = {"value": 0}

        def fake_step(**kwargs):
            step_counter["value"] += 1
            if step_counter["value"] == 1:
                return {
                    "episode_id": "ep-1",
                    "observation": "<returncode>0</returncode>\n<output>\nlib/rubocop/cop/style/block_delimiters.rb:1:test\n</output>",
                    "done": False,
                    "truncated": False,
                }
            if step_counter["value"] == 2:
                return {
                    "episode_id": "ep-1",
                    "observation": "<returncode>0</returncode>\n<output>\n# frozen_string_literal: true\nclass BlockDelimiters\n</output>",
                    "done": False,
                    "truncated": False,
                }
            return {"episode_id": "ep-1", "observation": "done", "done": True, "truncated": False}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis.openenv_step", fake_step)
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: {"episode_id": "ep-1", "observation": "state", "info": {"changed_files": []}},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._teacher_controller_decision",
            lambda **kwargs: (
                {"branch_decision": "CURRENT", "inject_teacher_think": False, "teacher_think_text": "", "reason": "stay current"},
                {"output_text": "{\"branch_decision\":\"CURRENT\",\"inject_teacher_think\":false,\"teacher_think_text\":\"\",\"reason\":\"stay current\"}"},
                "{\"branch_decision\":\"CURRENT\",\"inject_teacher_think\":false,\"teacher_think_text\":\"\",\"reason\":\"stay current\"}",
            ),
        )

        def fake_chat_completion(**kwargs):
            model = kwargs["model"]
            used_models.append(model)
            return {"choices": [{"message": {"content": next(responses[model])}}]}

        monkeypatch.setattr("orbit.integrations.affinetes_swe.synthesis._chat_completion", fake_chat_completion)

        result = run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="student-model",
            api_key="token",
            teacher_model="teacher-model",
            teacher_api_base="https://example.invalid/v1",
            teacher_api_key="token",
            max_steps=3,
            max_root_retries=0,
            max_edit_retries=0,
        )

        assert used_models == ["student-model", "student-model", "student-model"]
        assert result["student_calls"] == 3
        assert result["teacher_calls"] == 3
        assert result["teacher_branch_calls"] == 0
        assert result["teacher_think_calls"] == 0

    def test_teacher_current_decision_does_not_use_stale_stall_class_forced_rollback(self, monkeypatch, tmp_path):
        responses = iter(
            [
                "```bash\ncd /app && sed -i 's/old/new/' target.txt\n```",
                "```bash\ncd /app && sed -n '1,20p' target.txt\n```",
            ]
        )
        state_payloads = iter(
            [
                {
                    "episode_id": "ep-1",
                    "observation": "state-1",
                    "info": {
                        "changed_files": ["target.txt"],
                        "submission": {"diff_stat": " 1 file changed"},
                        "patch_hash": "patch-1",
                    },
                },
                {
                    "episode_id": "ep-1",
                    "observation": "state-2",
                    "info": {
                        "changed_files": ["target.txt"],
                        "submission": {"diff_stat": " 1 file changed"},
                        "patch_hash": "patch-1",
                    },
                },
            ]
        )
        decisions = iter(
            [
                (
                    {
                        "restore_target": "CURRENT",
                        "inject_teacher_think": False,
                        "teacher_think_text": "",
                        "stall_class": "none",
                        "reason": "stay current after first edit",
                    },
                    {"output_text": "{}"},
                    "{}",
                ),
                (
                    {
                        "restore_target": "CURRENT",
                        "inject_teacher_think": False,
                        "teacher_think_text": "",
                        "stall_class": "none",
                        "reason": "still current; verify only",
                    },
                    {"output_text": "{}"},
                    "{}",
                ),
            ]
        )
        restores: list[dict[str, object]] = []

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {
                "episode_id": "ep-1",
                "observation": "<pr_description>Fix target</pr_description>",
                "done": False,
                "truncated": False,
            },
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {
                "episode_id": "ep-1",
                "checkpoint_id": "baseline-ckpt" if kwargs.get("label") == "baseline" else "edit-ckpt",
            },
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_step",
            lambda **kwargs: {
                "episode_id": "ep-1",
                "observation": "<returncode>0</returncode><output>ok</output>",
                "done": False,
                "truncated": False,
            },
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: next(state_payloads),
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_restore",
            lambda **kwargs: restores.append(kwargs) or {"episode_id": "ep-1", "observation": "restored"},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._teacher_controller_decision",
            lambda **kwargs: next(decisions),
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._chat_completion",
            lambda **kwargs: {"choices": [{"message": {"content": next(responses)}}]},
        )

        result = run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="student-model",
            api_key="token",
            teacher_model="teacher-model",
            teacher_api_base="https://example.invalid/v1",
            teacher_api_key="token",
            max_steps=2,
            max_root_retries=1,
            max_edit_retries=1,
        )

        assert restores == []
        assert result["restore_target_applied"] == "CURRENT"

    def test_plausible_patch_protection_blocks_teacher_rollback_without_bad_stall(self, monkeypatch, tmp_path):
        responses = iter(
            [
                "```bash\ncd /app && sed -i 's/old/new/' target.txt\n```",
                "```bash\ncd /app && sed -n '1,20p' target.txt\n```",
            ]
        )
        state_payloads = iter(
            [
                {
                    "episode_id": "ep-1",
                    "observation": "state-1",
                    "info": {
                        "changed_files": ["target.txt"],
                        "submission": {"diff_stat": " 1 file changed"},
                        "patch_hash": "patch-1",
                    },
                },
                {
                    "episode_id": "ep-1",
                    "observation": "state-2",
                    "info": {
                        "changed_files": ["target.txt"],
                        "submission": {"diff_stat": " 1 file changed"},
                        "patch_hash": "patch-1",
                    },
                },
            ]
        )
        decisions = iter(
            [
                (
                    {
                        "restore_target": "CURRENT",
                        "inject_teacher_think": False,
                        "teacher_think_text": "",
                        "stall_class": "none",
                        "reason": "make the edit",
                    },
                    {"output_text": "{}"},
                    "{}",
                ),
                (
                    {
                        "restore_target": "ROLLBACK_1",
                        "inject_teacher_think": False,
                        "teacher_think_text": "",
                        "stall_class": "none",
                        "reason": "rollback even though patch looks plausible",
                    },
                    {"output_text": "{}"},
                    "{}",
                ),
            ]
        )
        restores: list[dict[str, object]] = []

        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_reset",
            lambda **kwargs: {
                "episode_id": "ep-1",
                "observation": "<pr_description>Fix target</pr_description>",
                "done": False,
                "truncated": False,
            },
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_checkpoint",
            lambda **kwargs: {
                "episode_id": "ep-1",
                "checkpoint_id": "baseline-ckpt" if kwargs.get("label") == "baseline" else "edit-ckpt",
            },
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_step",
            lambda **kwargs: {
                "episode_id": "ep-1",
                "observation": "<returncode>0</returncode><output>ok</output>",
                "done": False,
                "truncated": False,
            },
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_state",
            lambda **kwargs: next(state_payloads),
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_restore",
            lambda **kwargs: restores.append(kwargs) or {"episode_id": "ep-1", "observation": "restored"},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis.openenv_stop",
            lambda **kwargs: {"episode_id": "ep-1", "stopped": True},
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._teacher_controller_decision",
            lambda **kwargs: next(decisions),
        )
        monkeypatch.setattr(
            "orbit.integrations.affinetes_swe.synthesis._chat_completion",
            lambda **kwargs: {"choices": [{"message": {"content": next(responses)}}]},
        )

        result = run_openenv_synthesis(
            output_dir=str(tmp_path / "synth"),
            upstream_repo_path="/fake/upstream",
            upstream_ref="a" * 40,
            task_id="1",
            api_base="https://example.invalid/v1",
            model="student-model",
            api_key="token",
            teacher_model="teacher-model",
            teacher_api_base="https://example.invalid/v1",
            teacher_api_key="token",
            max_steps=2,
            max_root_retries=1,
            max_edit_retries=1,
        )

        assert restores == []
        assert result["restore_target_applied"] == "CURRENT"


class TestCliSurface:
    def test_cli_help_exposes_blackbox_subcommands(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["data", "swe-collect", "--help"])
        assert result.exit_code == 0
        assert "evaluate" in result.output
        assert "openenv" in result.output
        assert "sample" not in result.output
        assert "build-buckets" not in result.output

    def test_cli_help_exposes_openenv_reset(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["data", "swe-collect", "openenv", "reset", "--help"])
        assert result.exit_code == 0
        assert "--upstream-ref" in result.output
        assert "--task-id" in result.output

    def test_cli_help_exposes_openenv_checkpoint_restore(self):
        runner = CliRunner()
        reset_help = runner.invoke(cli, ["data", "swe-collect", "openenv", "reset", "--help"])
        checkpoint_help = runner.invoke(cli, ["data", "swe-collect", "openenv", "checkpoint", "--help"])
        restore_help = runner.invoke(cli, ["data", "swe-collect", "openenv", "restore", "--help"])
        state_help = runner.invoke(cli, ["data", "swe-collect", "openenv", "state", "--help"])
        assert reset_help.exit_code == 0
        assert "--api-key-file" in reset_help.output
        assert checkpoint_help.exit_code == 0
        assert "--label" in checkpoint_help.output
        assert restore_help.exit_code == 0
        assert "--checkpoint-id" in restore_help.output
        assert state_help.exit_code == 0
        assert "--episode-id" in state_help.output

    def test_cli_help_exposes_synthesize(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["data", "swe-collect", "synthesize", "--help"])
        assert result.exit_code == 0
        assert "--task-id" in result.output
        assert "--max-root-retries" in result.output
        assert "--max-edit-retries" in result.output
        assert "--teacher-model" in result.output
        assert "--reasoning-effort" in result.output
        assert "--teacher-reasoning-effort" in result.output
        assert "--probe-runtime / --no-probe-runtime" in result.output
        assert "--inject-teacher-think / --no-inject-teacher-think" in result.output
        assert "--student-enable-thinking / --no-student-enable-thinking" in result.output
        assert "--student-max-new-tokens" in result.output
        assert "--transport-only-retries" in result.output
        assert "--eval-mode / --no-eval-mode" in result.output
        assert "--eval-max-context-tokens" in result.output


class TestSynthesisHelpers:
    def test_classify_stall_does_not_flag_single_verify_after_patch(self):
        stall = synthesis_module._classify_stall(
            raw_action_text="```bash\ngit diff\n```",
            action_text="```bash\ngit diff\n```",
            command_signature="git diff",
            command_history=["sed -i 's/old/new/' target.txt", "git diff"],
            latest_changed_files=["target.txt"],
            same_patch_steps=1,
            patch_repeat_command_kind="verify",
        )
        assert stall == "none"

    def test_classify_stall_does_not_flag_single_read_after_patch(self):
        stall = synthesis_module._classify_stall(
            raw_action_text="```bash\nsed -n '1,20p' target.txt\n```",
            action_text="```bash\nsed -n '1,20p' target.txt\n```",
            command_signature="sed -n '1,20p' target.txt",
            command_history=["sed -i 's/old/new/' target.txt", "sed -n '1,20p' target.txt"],
            latest_changed_files=["target.txt"],
            same_patch_steps=1,
            patch_repeat_command_kind="read",
        )
        assert stall == "none"

    def test_classify_stall_flags_repeated_verify_after_patch(self):
        stall = synthesis_module._classify_stall(
            raw_action_text="```bash\ngit diff\n```",
            action_text="```bash\ngit diff\n```",
            command_signature="git diff",
            command_history=["git diff", "git diff"],
            latest_changed_files=["target.txt"],
            same_patch_steps=2,
            patch_repeat_command_kind="verify",
        )
        assert stall == "verify_loop"

    def test_cli_evaluate_runs_blackbox_wrapper(self, tmp_path):
        repo, commit = _init_fake_affinetes_repo(tmp_path)
        runner = CliRunner()

        result = runner.invoke(
            cli,
            [
                "data",
                "swe-collect",
                "evaluate",
                "--task-range",
                "1",
                "--upstream-repo-path",
                str(repo),
                "--upstream-ref",
                commit,
                "--agent",
                "miniswe",
                "--model",
                "demo-model",
                "--api-key",
                "token",
                "--output-dir",
                str(tmp_path / "run"),
            ],
        )

        assert result.exit_code == 0
        assert "SWE evaluate complete" in result.output
        assert (tmp_path / "run" / "manifests" / "run.json").exists()
