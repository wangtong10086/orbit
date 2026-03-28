"""Tests for Layer 0: forge/env — environment definitions and registry."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge.env.base import EnvProtocol, EnvSpec
from forge.env.gem import GemEnv, Observation, StepResult
from forge.env.registry import EnvRegistry, EnvHub
from forge.env.sandbox import Sandbox, SandboxConfig, SandboxStatus, ExecutionResult
from forge.foundation.environment_catalog import default_environment_catalog


# ── Registry ──

class TestEnvRegistry:
    def test_catalog_constructs_without_side_effect_imports(self):
        names = default_environment_catalog().list_data_envs()
        expected = {"GAME", "NAVWORLD", "SWE-INFINITE", "LIVEWEB", "LGC-v2", "PRINT"}
        assert expected.issubset(set(names)), f"Missing: {expected - set(names)}"

    def test_all_envs_registered(self):
        names = EnvRegistry.list_envs()
        expected = {"GAME", "NAVWORLD", "SWE-INFINITE", "LIVEWEB", "LGC-v2", "PRINT"}
        assert expected.issubset(set(names)), f"Missing: {expected - set(names)}"

    def test_make_returns_protocol(self):
        env = EnvRegistry.make("GAME")
        assert hasattr(env, "validate_entry")
        assert hasattr(env, "clean_entry")
        assert hasattr(env, "spec")

    def test_make_unknown_raises(self):
        try:
            EnvRegistry.make("NONEXISTENT")
            assert False, "Should have raised KeyError"
        except KeyError:
            pass

    def test_has(self):
        assert EnvRegistry.has("GAME")
        assert not EnvRegistry.has("NONEXISTENT")

    def test_get_returns_class(self):
        cls = EnvRegistry.get("GAME")
        assert cls is not None


# ── GameEnv ──

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
        env = EnvRegistry.make("GAME")
        issues = env.validate_entry(self._make_valid())
        assert issues == [], f"Unexpected issues: {issues}"

    def test_validate_missing_messages(self):
        env = EnvRegistry.make("GAME")
        issues = env.validate_entry({"env": "GAME", "score": 0.5})
        assert len(issues) > 0

    def test_validate_wrong_env(self):
        env = EnvRegistry.make("GAME")
        entry = self._make_valid()
        entry["env"] = "NAVWORLD"
        issues = env.validate_entry(entry)
        assert any("env" in i.lower() for i in issues)

    def test_clean_valid_keeps(self):
        env = EnvRegistry.make("GAME")
        result = env.clean_entry(self._make_valid())
        assert result is not None
        assert len(result["messages"]) == 3

    def test_clean_too_few_messages_drops(self):
        env = EnvRegistry.make("GAME")
        entry = {
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
            "env": "GAME",
            "score": 0.5,
        }
        result = env.clean_entry(entry)
        assert result is None, "Should drop < 3 messages"

    def test_clean_no_system_first_drops(self):
        env = EnvRegistry.make("GAME")
        entry = {
            "messages": [
                {"role": "user", "content": "Play chess"},
                {"role": "assistant", "content": "I'll play e4."},
                {"role": "user", "content": "Your turn"},
            ],
            "env": "GAME",
            "score": 0.5,
        }
        result = env.clean_entry(entry)
        assert result is None, "Should drop if system not first"

    def test_spec_weight(self):
        env = EnvRegistry.make("GAME")
        assert env.spec.scoring_weight == 3.0


# ── NavworldEnv ──

class TestNavworldEnv:
    def _make_valid(self):
        return {
            "messages": [
                {"role": "system", "content": "你是一个旅行规划助手。"},
                {"role": "user", "content": "帮我规划从北京到上海的旅行"},
                {"role": "assistant", "content": "好的，让我调用工具帮您查询poi_search相关信息。", "tool_calls": [{"id": "1", "function": {"name": "search_flights", "arguments": "{}"}}]},
                {"role": "tool", "content": '{"flights": []}', "tool_call_id": "1"},
                {"role": "assistant", "content": "让我再调用工具查询search_train_tickets火车票和around_search周边。", "tool_calls": [{"id": "2", "function": {"name": "search_train_tickets", "arguments": "{}"}}]},
                {"role": "tool", "content": '{"trains": []}', "tool_call_id": "2"},
                {"role": "assistant", "content": "让我调用工具查看weather天气情况和direction路线。", "tool_calls": [{"id": "3", "function": {"name": "weather", "arguments": "{}"}}]},
                {"role": "tool", "content": '{"weather": "sunny"}', "tool_call_id": "3"},
                {"role": "assistant", "content": "根据查询结果，我建议您考虑以下旅行方案。综合对比各种交通方式，推荐您选择高铁出行。因为高铁既快速又舒适，适合您的行程安排。" + "x" * 200},
            ],
            "env": "NAVWORLD",
            "score": 0.8,
        }

    def test_validate_valid(self):
        env = EnvRegistry.make("NAVWORLD")
        issues = env.validate_entry(self._make_valid())
        assert issues == [], f"Unexpected issues: {issues}"

    def test_clean_valid_keeps(self):
        env = EnvRegistry.make("NAVWORLD")
        result = env.clean_entry(self._make_valid())
        assert result is not None

    def test_clean_too_few_msgs_drops(self):
        env = EnvRegistry.make("NAVWORLD")
        entry = {
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
            "env": "NAVWORLD",
        }
        result = env.clean_entry(entry)
        assert result is None

    def test_allowed_extra_fields(self):
        env = EnvRegistry.make("NAVWORLD")
        assert "tool_calls" in env.spec.allowed_extra_fields
        assert "tool" in env.spec.valid_roles


# ── SweEnv ──

class TestSweEnv:
    def _make_valid(self):
        return {
            "messages": [
                {"role": "system", "content": "You are a code assistant."},
                {"role": "user", "content": "Fix this bug in the code"},
                {"role": "assistant", "content": "I'll analyze the code and fix the issue by implementing a proper solution."},
                {"role": "user", "content": "Here is another file"},
                {"role": "assistant", "content": "I've fixed the bug by correcting the logic."},
            ],
            "env": "SWE-INFINITE",
            "score": 0.9,
        }

    def test_validate_valid(self):
        env = EnvRegistry.make("SWE-INFINITE")
        issues = env.validate_entry(self._make_valid())
        assert issues == [], f"Unexpected issues: {issues}"

    def test_clean_valid_keeps(self):
        env = EnvRegistry.make("SWE-INFINITE")
        result = env.clean_entry(self._make_valid())
        assert result is not None

    def test_clean_too_few_drops(self):
        env = EnvRegistry.make("SWE-INFINITE")
        entry = {
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
            "env": "SWE-INFINITE",
        }
        result = env.clean_entry(entry)
        assert result is None


# ── LgcEnv ──

class TestLgcEnv:
    def _make_valid(self):
        return {
            "messages": [
                {"role": "user", "content": "Solve this logic puzzle: If A then B."},
                {"role": "assistant", "content": "<think>Let me reason through this step by step.</think>The answer is B must be true."},
            ],
            "env": "LGC-v2",
            "score": 1.0,
        }

    def test_validate_valid(self):
        env = EnvRegistry.make("LGC-v2")
        issues = env.validate_entry(self._make_valid())
        assert issues == [], f"Unexpected issues: {issues}"

    def test_clean_valid_keeps(self):
        env = EnvRegistry.make("LGC-v2")
        result = env.clean_entry(self._make_valid())
        assert result is not None

    def test_clean_wrong_msg_count_drops(self):
        env = EnvRegistry.make("LGC-v2")
        entry = {
            "messages": [
                {"role": "user", "content": "q1"},
                {"role": "assistant", "content": "<think>ok</think>A"},
                {"role": "user", "content": "q2"},
            ],
            "env": "LGC-v2",
        }
        result = env.clean_entry(entry)
        assert result is None, "Should drop != 2 messages"

    def test_clean_unbalanced_think_drops(self):
        env = EnvRegistry.make("LGC-v2")
        entry = {
            "messages": [
                {"role": "user", "content": "puzzle"},
                {"role": "assistant", "content": "<think>reasoning without closing tag"},
            ],
            "env": "LGC-v2",
        }
        result = env.clean_entry(entry)
        assert result is None, "Should drop unbalanced think tags"


# ── PrintEnv ──

class TestPrintEnv:
    def _make_valid(self):
        return {
            "messages": [
                {"role": "user", "content": "What does this code print? print(2+2)"},
                {"role": "assistant", "content": "<think>2+2=4</think>4"},
            ],
            "env": "PRINT",
            "score": 1.0,
        }

    def test_validate_valid(self):
        env = EnvRegistry.make("PRINT")
        issues = env.validate_entry(self._make_valid())
        assert issues == [], f"Unexpected issues: {issues}"

    def test_clean_valid_keeps(self):
        env = EnvRegistry.make("PRINT")
        result = env.clean_entry(self._make_valid())
        assert result is not None

    def test_clean_no_answer_after_think_drops(self):
        env = EnvRegistry.make("PRINT")
        entry = {
            "messages": [
                {"role": "user", "content": "What does this print?"},
                {"role": "assistant", "content": "<think>reasoning</think>"},
            ],
            "env": "PRINT",
        }
        result = env.clean_entry(entry)
        assert result is None, "Should drop if no answer after think"


# ── LivewebEnv ──

class TestLivewebEnv:
    def _make_valid(self):
        return {
            "messages": [
                {"role": "system", "content": "You are a web browser agent."},
                {"role": "user", "content": "Go to google.com"},
                {"role": "assistant", "content": "I'll navigate to google.com."},
            ],
            "env": "LIVEWEB",
            "score": 0.7,
        }

    def test_validate_valid(self):
        env = EnvRegistry.make("LIVEWEB")
        issues = env.validate_entry(self._make_valid())
        assert issues == [], f"Unexpected issues: {issues}"

    def test_clean_valid_keeps(self):
        env = EnvRegistry.make("LIVEWEB")
        result = env.clean_entry(self._make_valid())
        assert result is not None

    def test_clean_no_assistant_drops(self):
        env = EnvRegistry.make("LIVEWEB")
        entry = {
            "messages": [
                {"role": "user", "content": "Go to google.com"},
                {"role": "user", "content": "Click the button"},
            ],
            "env": "LIVEWEB",
        }
        result = env.clean_entry(entry)
        assert result is None


# ── Sandbox API ──

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

    def test_custom(self):
        r = ExecutionResult(stdout="ok", stderr="warn", exit_code=1, timed_out=True)
        assert r.stdout == "ok"
        assert r.exit_code == 1
        assert r.timed_out is True


class TestSandbox:
    def test_initial_status(self):
        sb = Sandbox()
        assert sb.status == SandboxStatus.CREATED
        assert sb.sandbox_id is None
        assert sb.is_alive() is False

    def test_start_sets_running(self):
        sb = Sandbox(SandboxConfig(image="test:latest"))
        asyncio.run(sb.start())
        assert sb.status == SandboxStatus.RUNNING
        assert sb.sandbox_id is not None
        assert sb.is_alive() is True

    def test_stop_sets_stopped(self):
        sb = Sandbox()
        asyncio.run(sb.start())
        asyncio.run(sb.stop())
        assert sb.status == SandboxStatus.STOPPED
        assert sb.is_alive() is False

    def test_execute_when_running(self):
        sb = Sandbox()
        asyncio.run(sb.start())
        result = asyncio.run(sb.execute("echo hi"))
        assert isinstance(result, ExecutionResult)
        assert result.exit_code == 0

    def test_execute_when_not_running_raises(self):
        sb = Sandbox()
        try:
            asyncio.run(sb.execute("echo hi"))
            assert False, "Should raise RuntimeError"
        except RuntimeError as e:
            assert "not running" in str(e).lower()

    def test_config_preserved(self):
        cfg = SandboxConfig(image="my-image", memory="32g")
        sb = Sandbox(cfg)
        assert sb.config is cfg
        assert sb.config.image == "my-image"


# ── GEM Protocol ──

class TestObservation:
    def test_defaults(self):
        obs = Observation(text="hello")
        assert obs.text == "hello"
        assert obs.metadata == {}

    def test_with_metadata(self):
        obs = Observation(text="test", metadata={"key": "value"})
        assert obs.metadata["key"] == "value"


class TestStepResult:
    def test_defaults(self):
        obs = Observation(text="x")
        sr = StepResult(observation=obs)
        assert sr.reward == 0.0
        assert sr.terminated is False
        assert sr.truncated is False
        assert sr.info == {}

    def test_as_tuple(self):
        obs = Observation(text="x")
        sr = StepResult(observation=obs, reward=1.0, terminated=True, info={"a": 1})
        tup = sr.as_tuple()
        assert len(tup) == 5
        assert tup[0] is obs
        assert tup[1] == 1.0
        assert tup[2] is True
        assert tup[3] is False
        assert tup[4] == {"a": 1}


class TestGemEnvBase:
    def test_base_reset_raises(self):
        env = GemEnv()
        try:
            env.reset()
            assert False, "Should raise NotImplementedError"
        except NotImplementedError:
            pass

    def test_base_step_raises(self):
        env = GemEnv()
        try:
            env.step("action")
            assert False, "Should raise NotImplementedError"
        except NotImplementedError:
            pass

    def test_base_close_noop(self):
        env = GemEnv()
        env.close()  # Should not raise

    def test_base_not_interactive(self):
        env = GemEnv()
        assert env.is_interactive is False


class TestGameGemEnv:
    def test_reset(self):
        env = EnvHub.make_gem("GAME")
        obs, info = env.reset(seed=123)
        assert isinstance(obs, Observation)
        assert "game" in obs.text.lower() or "chess" in obs.text.lower()
        assert "game" in info

    def test_step(self):
        env = EnvHub.make_gem("GAME")
        env.reset()
        result = env.step("e2e4")
        assert isinstance(result, StepResult)
        assert isinstance(result.observation, Observation)

    def test_is_interactive(self):
        env = EnvHub.make_gem("GAME")
        assert env.is_interactive is True


class TestNavworldGemEnv:
    def test_reset_and_step(self):
        env = EnvHub.make_gem("NAVWORLD")
        obs, info = env.reset()
        assert isinstance(obs, Observation)
        result = env.step("search flights")
        assert isinstance(result, StepResult)

    def test_is_interactive(self):
        env = EnvHub.make_gem("NAVWORLD")
        assert env.is_interactive is True


class TestSweGemEnv:
    def test_reset_and_step(self):
        env = EnvHub.make_gem("SWE-INFINITE")
        obs, info = env.reset()
        assert isinstance(obs, Observation)
        result = env.step("fix bug")
        assert isinstance(result, StepResult)


# ── EnvHub ──

class TestEnvHub:
    def test_all_gem_envs_registered(self):
        names = EnvHub.list_gem_envs()
        expected = {"GAME", "NAVWORLD", "SWE-INFINITE", "LIVEWEB", "LGC-v2", "PRINT"}
        assert expected.issubset(set(names)), f"Missing GEM: {expected - set(names)}"

    def test_make_gem_returns_gem_env(self):
        env = EnvHub.make_gem("GAME")
        assert isinstance(env, GemEnv)
        assert hasattr(env, "reset")
        assert hasattr(env, "step")
        assert hasattr(env, "close")

    def test_make_gem_unknown_raises(self):
        try:
            EnvHub.make_gem("NONEXISTENT")
            assert False, "Should raise KeyError"
        except KeyError:
            pass

    def test_make_data_delegates(self):
        env = EnvHub.make_data("GAME")
        assert hasattr(env, "validate_entry")
        assert hasattr(env, "clean_entry")

    def test_has_gem(self):
        assert EnvHub.has_gem("GAME")
        assert EnvHub.has_gem("NAVWORLD")
        assert not EnvHub.has_gem("NONEXISTENT")

    def test_list_data_envs(self):
        names = EnvHub.list_data_envs()
        assert "GAME" in names
        assert "NAVWORLD" in names

    def test_list_all(self):
        result = EnvHub.list_all()
        assert "data" in result
        assert "gem" in result
        assert isinstance(result["data"], list)
        assert isinstance(result["gem"], list)
        assert "GAME" in result["data"]
        assert "GAME" in result["gem"]
