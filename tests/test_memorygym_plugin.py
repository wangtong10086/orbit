from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace


PLUGIN_PATH = Path(__file__).resolve().parents[1] / "scripts" / "memorygym_ms_swift_plugin.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeMemoryEnv:
    write_budget = 7

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False
        self.actions: list[dict] = []

    def reset(self, seed=None):
        self.seed = seed
        return "FIRST_OBS"

    def step(self, action):
        self.actions.append(action)
        if action["tool"] == "next":
            return "SECOND_OBS", 0.0, False, {"episode_stats": {"questions_answered": 0}}
        return "DONE_OBS", 1.0, True, {"episode_stats": {"questions_answered": 1}}

    def get_verifiable_reward(self):
        return 0.37

    def close(self):
        self.closed = True


def _infer_request():
    return SimpleNamespace(
        data_dict={
            "episode_id": "ep-001",
            "env_config": {"template_name": "company", "tier": "lite", "seed": 23},
        }
    )


def test_env_pack_definition_exposes_memorygym_contract():
    from orbit_env_memorygym.api import get_env_pack_definition

    definition = get_env_pack_definition()

    assert definition.env_pack_id == "memorygym"
    assert definition.episode_loop_version == "memorygym.loop.v1"
    assert definition.reward_semantics_version == "memorygym.verifiable_reward.v1"
    assert "parsed_action" in definition.telemetry_fields


def test_memorygym_codec_falls_back_to_next(monkeypatch):
    from orbit_env_memorygym import codec

    class _CommonModule:
        @staticmethod
        def parse_tool_calls(text):
            return []

    monkeypatch.setitem(__import__("sys").modules, "memorygym.adapters._common", _CommonModule)
    assert codec.parse_memorygym_action("no tool call") == {"tool": "next"}


def test_env_step_uses_env_pack_reward_and_telemetry(monkeypatch):
    from orbit_env_memorygym.swift_plugin import MemoryGymEnv

    fake_env = _FakeMemoryEnv()

    class _CommonModule:
        @staticmethod
        def get_system_prompt(budget):
            return f"SYSTEM PROMPT budget={budget}"

    class _TrainingModule:
        @staticmethod
        def MemoryEnv(**kwargs):
            return fake_env

    monkeypatch.setitem(__import__("sys").modules, "memorygym.adapters._common", _CommonModule)
    monkeypatch.setitem(__import__("sys").modules, "memorygym.training", _TrainingModule)
    monkeypatch.setattr(
        "orbit_env_memorygym.swift_plugin.parse_memorygym_action",
        lambda text: {"tool": "submit_answer", "args": {"answer": "Paris"}},
    )

    env = MemoryGymEnv({"template_name": "company", "tier": "lite", "seed": 0})
    observation, info, system_message = asyncio.run(env.reset(_infer_request()))

    assert observation == "FIRST_OBS"
    assert system_message == "SYSTEM PROMPT budget=7"
    assert info == {"template": "company", "tier": "lite", "seed": 23, "terminated": False}

    next_obs, reward, done, telemetry = asyncio.run(
        env.step([{"role": "assistant", "content": "<tool_call>...</tool_call>"}])
    )

    assert fake_env.actions == [{"tool": "submit_answer", "args": {"answer": "Paris"}}]
    assert next_obs == "Episode complete."
    assert reward == 0.37
    assert done is True
    assert telemetry["parsed_action"] == {"tool": "submit_answer", "args": {"answer": "Paris"}}
    assert telemetry["template"] == "company"


def test_env_close_closes_underlying_memory_env():
    from orbit_env_memorygym.swift_plugin import MemoryGymEnv

    fake_env = _FakeMemoryEnv()
    env = MemoryGymEnv({})
    env._env = fake_env
    asyncio.run(env.close())

    assert fake_env.closed is True
    assert env._env is None


def test_plugin_shim_imports_cleanly():
    module = _load_module("memorygym_ms_swift_plugin_test", PLUGIN_PATH)
    assert module is not None


def test_register_ms_swift_plugin_keeps_memorygym_alias():
    from orbit_env_memorygym.swift_plugin import envs, register_ms_swift_plugin

    envs.pop("MEMORYGYM", None)
    envs.pop("memorygym_env", None)
    register_ms_swift_plugin()

    assert envs["memorygym_env"] is envs["MEMORYGYM"]


def test_plugin_shim_prefers_staged_runtime_package_source():
    source = PLUGIN_PATH.read_text(encoding="utf-8")

    assert 'for candidate in sorted(BUNDLE_INPUTS.glob("runtime-package-*")):' in source
    assert 'if (candidate_src / "orbit_env_memorygym").exists():' in source
