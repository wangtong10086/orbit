"""Tests for Layer 0: forge/env — environment definitions via EnvironmentCatalog."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge.env.base import EnvProtocol, EnvSpec
from forge.env.gem import GemEnv, Observation, StepResult
from forge.env.sandbox import Sandbox, SandboxConfig, SandboxStatus, ExecutionResult
from forge.foundation.environment_catalog import default_environment_catalog


CATALOG = default_environment_catalog()


def _data_env(name: str):
    return CATALOG.make_data(name)


def _gem_env(name: str):
    return CATALOG.make_gem(name)


class TestEnvironmentCatalog:
    def test_catalog_constructs_without_side_effect_imports(self):
        names = CATALOG.list_data_envs()
        expected = {"GAME", "NAVWORLD", "SWE-INFINITE", "LIVEWEB", "LGC-v2", "PRINT"}
        assert expected.issubset(set(names)), f"Missing: {expected - set(names)}"

    def test_get_data_class(self):
        cls = CATALOG.get_data_class("GAME")
        assert cls is not None

    def test_get_unknown_raises(self):
        try:
            CATALOG.make_data("NONEXISTENT")
            assert False, "Should raise KeyError"
        except KeyError:
            pass

    def test_gem_envs_listed(self):
        names = CATALOG.list_gem_envs()
        expected = {"GAME", "NAVWORLD", "SWE-INFINITE", "LIVEWEB", "LGC-v2", "PRINT"}
        assert expected.issubset(set(names)), f"Missing GEM: {expected - set(names)}"


class TestGameEnv:
    def _make_valid(self):
        return {
            "messages": [
                {"role": "system", "content": "You are a game player."},
                {"role": "user", "content": "Play chess"},
                {"role": "assistant", "content": "I'll play e4."},
            ],
            "env": "GAME",
            "score": 0.5,
        }

    def test_validate_valid_entry(self):
        env = _data_env("GAME")
        issues = env.validate_entry(self._make_valid())
        assert issues == []

    def test_clean_valid_keeps(self):
        env = _data_env("GAME")
        result = env.clean_entry(self._make_valid())
        assert result is not None
        assert env.spec.scoring_weight == 3.0


class TestNavworldEnv:
    def _make_valid(self):
        return {
            "messages": [
                {"role": "system", "content": "你是一个旅行规划助手。"},
                {"role": "user", "content": "帮我规划从北京到上海的旅行"},
                {
                    "role": "assistant",
                    "content": "好的，让我调用工具帮您查询poi_search相关信息。",
                    "tool_calls": [{"id": "1", "function": {"name": "search_flights", "arguments": "{}"}}],
                },
                {"role": "tool", "content": '{"flights": []}', "tool_call_id": "1"},
                {
                    "role": "assistant",
                    "content": "让我再调用工具查询search_train_tickets火车票和around_search周边。",
                    "tool_calls": [{"id": "2", "function": {"name": "search_train_tickets", "arguments": "{}"}}],
                },
                {"role": "tool", "content": '{"trains": []}', "tool_call_id": "2"},
                {
                    "role": "assistant",
                    "content": "让我调用工具查看weather天气情况和direction路线。",
                    "tool_calls": [{"id": "3", "function": {"name": "weather", "arguments": "{}"}}],
                },
                {"role": "tool", "content": '{"weather": "sunny"}', "tool_call_id": "3"},
                {"role": "assistant", "content": "根据查询结果，我建议您考虑以下旅行方案。综合对比各种交通方式，推荐您选择高铁出行。因为高铁既快速又舒适，适合您的行程安排。" + "x" * 200},
            ],
            "env": "NAVWORLD",
            "score": 0.8,
        }

    def test_validate_valid(self):
        env = _data_env("NAVWORLD")
        issues = env.validate_entry(self._make_valid())
        assert issues == []

    def test_clean_valid_keeps(self):
        env = _data_env("NAVWORLD")
        result = env.clean_entry(self._make_valid())
        assert result is not None
        assert "tool_calls" in env.spec.allowed_extra_fields
        assert "tool" in env.spec.valid_roles


class TestSweEnv:
    def test_validate_and_clean(self):
        env = _data_env("SWE-INFINITE")
        entry = {
            "messages": [
                {"role": "system", "content": "You are a code assistant."},
                {"role": "user", "content": "Fix this bug in the code"},
                {"role": "assistant", "content": "I'll analyze the code and fix the issue."},
                {"role": "user", "content": "Here is another file"},
                {"role": "assistant", "content": "I've fixed the bug."},
            ],
            "env": "SWE-INFINITE",
            "score": 0.9,
        }
        assert env.validate_entry(entry) == []
        assert env.clean_entry(entry) is not None


class TestLgcEnv:
    def test_validate_and_clean(self):
        env = _data_env("LGC-v2")
        entry = {
            "messages": [
                {"role": "user", "content": "Solve this logic puzzle: If A then B."},
                {"role": "assistant", "content": "<think>Let me reason through this step by step.</think>The answer is B must be true."},
            ],
            "env": "LGC-v2",
            "score": 1.0,
        }
        assert env.validate_entry(entry) == []
        assert env.clean_entry(entry) is not None


class TestPrintEnv:
    def test_validate_and_clean(self):
        env = _data_env("PRINT")
        entry = {
            "messages": [
                {"role": "user", "content": "What does this code print? print(2+2)"},
                {"role": "assistant", "content": "<think>2+2=4</think>4"},
            ],
            "env": "PRINT",
            "score": 1.0,
        }
        assert env.validate_entry(entry) == []
        assert env.clean_entry(entry) is not None


class TestLivewebEnv:
    def test_validate_and_clean(self):
        env = _data_env("LIVEWEB")
        entry = {
            "messages": [
                {"role": "system", "content": "You are a web browser agent."},
                {"role": "user", "content": "Go to google.com"},
                {"role": "assistant", "content": "I'll navigate to google.com."},
            ],
            "env": "LIVEWEB",
            "score": 0.7,
        }
        assert env.validate_entry(entry) == []
        assert env.clean_entry(entry) is not None


class TestSandboxConfig:
    def test_defaults(self):
        cfg = SandboxConfig()
        assert cfg.image == "python:3.11"
        assert cfg.memory == "8g"
        assert cfg.cpus == 2.0
        assert cfg.gpu == ""
        assert cfg.timeout == 300
        assert cfg.env_vars == {}
        assert cfg.working_dir == "/workspace"
        assert cfg.network_enabled is True

    def test_custom(self):
        cfg = SandboxConfig(image="cuda:12.0", memory="16g", gpu="A100", timeout=600)
        assert cfg.image == "cuda:12.0"
        assert cfg.gpu == "A100"
        assert cfg.timeout == 600


class TestSandboxStatus:
    def test_all_states(self):
        states = {s.value for s in SandboxStatus}
        assert states == {"created", "starting", "running", "stopping", "stopped", "error"}


class TestExecutionResult:
    def test_defaults(self):
        r = ExecutionResult()
        assert r.stdout == ""
        assert r.stderr == ""
        assert r.exit_code == 0
        assert r.timed_out is False


class TestSandbox:
    def test_lifecycle_and_execute(self):
        sb = Sandbox()
        assert sb.status == SandboxStatus.CREATED
        asyncio.run(sb.start())
        assert sb.status == SandboxStatus.RUNNING
        result = asyncio.run(sb.execute("echo hi"))
        assert isinstance(result, ExecutionResult)
        assert result.exit_code == 0
        asyncio.run(sb.stop())
        assert sb.status == SandboxStatus.STOPPED


class TestObservation:
    def test_defaults(self):
        obs = Observation(text="hello")
        assert obs.text == "hello"
        assert obs.metadata == {}


class TestStepResult:
    def test_as_tuple(self):
        obs = Observation(text="x")
        sr = StepResult(observation=obs, reward=1.0, terminated=True, info={"a": 1})
        tup = sr.as_tuple()
        assert len(tup) == 5
        assert tup[0] is obs
        assert tup[1] == 1.0
        assert tup[2] is True


class TestGemEnvBase:
    def test_base_methods(self):
        env = GemEnv()
        try:
            env.reset()
            assert False, "Should raise NotImplementedError"
        except NotImplementedError:
            pass
        try:
            env.step("action")
            assert False, "Should raise NotImplementedError"
        except NotImplementedError:
            pass
        env.close()
        assert env.is_interactive is False


class TestGemEnvironments:
    def test_game_gem(self):
        env = _gem_env("GAME")
        obs, info = env.reset(seed=123)
        assert isinstance(env, GemEnv)
        assert isinstance(obs, Observation)
        result = env.step("e2e4")
        assert isinstance(result, StepResult)

    def test_navworld_gem(self):
        env = _gem_env("NAVWORLD")
        obs, info = env.reset()
        assert isinstance(obs, Observation)
        result = env.step("search flights")
        assert isinstance(result, StepResult)

    def test_swe_gem(self):
        env = _gem_env("SWE-INFINITE")
        obs, info = env.reset()
        assert isinstance(obs, Observation)
        result = env.step("fix bug")
        assert isinstance(result, StepResult)
