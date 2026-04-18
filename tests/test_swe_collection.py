"""Tests for black-box upstream affinetes SWE-INFINITE integration."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

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
from orbit.integrations.affinetes_swe.runner import prepare_upstream_runtime
from orbit.integrations.affinetes_swe.runner import _server_socket_path
from orbit.tasks.collection.specs import SweCollectConfig


def _run(cmd: list[str], *, cwd: Path) -> str:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=True)
    return proc.stdout.strip()


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


class TestUpstreamRuntime:
    def test_openenv_server_socket_path_is_short(self, tmp_path):
        output_dir = tmp_path / ("nested-" * 12) / "run"
        socket_path = _server_socket_path(str(output_dir))
        assert str(socket_path).startswith("/tmp/orbit-openenv-")
        assert len(str(socket_path)) < 100

    def test_prepare_upstream_runtime_accepts_clean_repo(self, tmp_path):
        repo, commit = _init_fake_affinetes_repo(tmp_path)

        prepared = prepare_upstream_runtime(
            output_dir=str(tmp_path / "run"),
            upstream_repo_path=str(repo),
            upstream_ref=commit,
        )

        assert prepared.repo_root == repo.resolve()
        assert prepared.upstream_ref == commit
        assert prepared.python_bin.exists()

    def test_prepare_upstream_runtime_rejects_dirty_repo(self, tmp_path):
        repo, commit = _init_fake_affinetes_repo(tmp_path)
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

    def test_prepare_upstream_runtime_clone_mode_uses_exact_ref(self, tmp_path):
        repo, commit = _init_fake_affinetes_repo(tmp_path)

        prepared = prepare_upstream_runtime(
            output_dir=str(tmp_path / "run"),
            upstream_git_url=str(repo),
            upstream_ref=commit,
        )

        assert prepared.repo_root.exists()
        assert (prepared.repo_root / "environments" / "SWE-INFINITE" / "env.py").exists()


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
                return {"episode_id": "ep-1", "observation": "<returncode>0</returncode><output>edited</output>", "done": False, "truncated": False}
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
        assert any(kind == "restore" for kind, _ in calls)
        manifest = json.loads((tmp_path / "synth" / "manifests" / "synthesis_run.json").read_text(encoding="utf-8"))
        assert manifest["root_retries_used"] == 1

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
        prompts: list[str] = []
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
            lambda **kwargs: {"episode_id": "ep-1", "observation": "noop", "done": False, "truncated": False},
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
            prompts.append(kwargs["messages"][1]["content"])
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

        assert any("Avoid repeating these no-progress commands" in prompt for prompt in prompts[1:])
        assert any("cd /app && ls" in prompt for prompt in prompts[1:])

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

    def test_synthesis_after_file_view_prompts_for_edit(self, monkeypatch, tmp_path):
        prompts: list[str] = []
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
            prompts.append(kwargs["messages"][1]["content"])
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

        assert any("must make one minimal non-interactive edit" in prompt for prompt in prompts[1:])
        assert any("lib/rubocop/cop/style/block_delimiters.rb" in prompt for prompt in prompts[1:])
        assert any("ruby - <<'RUBY'" in prompt for prompt in prompts[1:])

    def test_synthesis_after_failed_edit_stays_on_same_file_and_avoids_restore(self, monkeypatch, tmp_path):
        prompts: list[str] = []
        restores: list[dict] = []
        responses = iter(
            [
                "```bash\ncd /app && sed -n '1,40p' lib/rubocop/cop/style/block_delimiters.rb\n```",
                "```bash\npython - <<'PY'\nprint('edit')\nPY\n```",
                "```bash\nruby -e 'print :ok'\n```",
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
            prompts.append(kwargs["messages"][1]["content"])
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

        assert restores == []
        assert any("`python` is unavailable" in prompt for prompt in prompts[2:])
        assert any("Do not search again" in prompt for prompt in prompts[2:])

    def test_synthesis_restores_edited_checkpoint_after_repeated_verify_with_same_patch(self, monkeypatch, tmp_path):
        restores: list[dict] = []
        responses = iter(
            [
                "```bash\ncd /app && sed -n '1,40p' release_notes.py\n```",
                "```bash\npython - <<'PY'\nfrom pathlib import Path\np = Path('release_notes.py')\ns = p.read_text()\np.write_text(s + '\\n# edit\\n')\nPY\n```",
                "```bash\npython -m py_compile release_notes.py\n```",
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
            max_steps=3,
            max_root_retries=0,
            max_edit_retries=1,
        )

        assert restores == [{"output_dir": str(tmp_path / "synth"), "episode_id": "ep-1", "checkpoint_id": "post-edit-2-ckpt"}]

    def test_synthesis_uses_teacher_model_for_edit_guidance(self, monkeypatch, tmp_path):
        used_models: list[str] = []
        responses = {
            "student-model": iter(
                [
                    "```bash\ncd /app && git grep -n \"BlockDelimiters\" lib spec\n```",
                    "```bash\ncd /app && sed -n '1,40p' lib/rubocop/cop/style/block_delimiters.rb\n```",
                ]
            ),
            "teacher-model": iter(
                [
                    "```bash\nruby - <<'RUBY'\nputs 'edit'\nRUBY\n```",
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

        assert used_models == ["student-model", "student-model", "teacher-model"]
        assert result["student_calls"] == 2
        assert result["teacher_calls"] == 1


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
