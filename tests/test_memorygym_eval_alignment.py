"""Verify MemoryGym training env aligns with online evaluation.

Tests cover: tier defaults, thinking strip, tool-result feedback,
context redaction, scoring alignment, and system-prompt budget.
Uses lightweight mocks where heavy backends (chromadb, markdown) are
unavailable.
"""

from __future__ import annotations

import asyncio
import re
import sys
import pathlib
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

_MEMORYGYM_ROOT = pathlib.Path(__file__).resolve().parents[1] / "repos" / "MemoryGym"
if str(_MEMORYGYM_ROOT) not in sys.path:
    sys.path.insert(0, str(_MEMORYGYM_ROOT))

from memorygym.protocol import TIERS, compute_axis_scores, WEIGHTS
from memorygym.adapters._common import parse_tool_calls, _try_parse_json

from orbit_env_memorygym.swift_plugin import (
    MemoryGymEnv,
    MemoryGymRedactContext,
    MemoryGymPassthroughContext,
    _THINK_RE,
    _EVENT_BOUNDARY_RE,
    _env_defaults,
)
from orbit_env_memorygym.codec import parse_memorygym_action


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEED = 42
TEMPLATE = "company"


class FakeInferRequest:
    def __init__(self, data_dict=None):
        self.data_dict = data_dict or {}
        self.uuid = f"test-{SEED}"
        self.messages = []


class _FakeMemoryEnv:
    """Lightweight mock for MemoryEnv (no heavy backend deps)."""

    write_budget = 30
    n_entities = 60

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._writes_used = 0
        self._stored_entity_names: set[str] = set()
        self._by_competency: dict[str, list[bool]] = {}
        self._event_idx = 0
        self._stream = [
            {"type": "ingest", "entity_names": ["Alice", "Bob"]},
            {"type": "question", "question": "Who is Alice?", "answer": "CEO",
             "competency": "retrieval"},
            {"type": "correction", "notice": "Bob changed role"},
            {"type": "question", "question": "What happened?", "answer": "He quit",
             "competency": "update"},
        ]

    def reset(self, seed=None):
        self._event_idx = 0
        self._writes_used = 0
        self._stored_entity_names = set()
        self._by_competency = {}
        return "=== Event 1/4 [DOCUMENTS] ===\n\nAlice: CEO, Bob: CTO"

    def step(self, action):
        tool = action.get("tool", "next")
        info: dict[str, Any] = {"episode_stats": {"questions_answered": 0}}

        if tool in ("Write", "memory_store"):
            content = action.get("args", {}).get("content", "")
            self._writes_used += 1
            info["memory_id"] = f"mem_{self._writes_used:03d}"
            info["remaining"] = self.write_budget - self._writes_used
            for name in ["Alice", "Bob"]:
                if name.lower() in content.lower():
                    self._stored_entity_names.add(name)
        elif tool == "memory_search":
            info["results"] = [{"id": "mem_001", "content": "Alice: CEO"}]
        elif tool == "submit_answer":
            event = self._stream[self._event_idx] if self._event_idx < len(self._stream) else None
            if event and event["type"] == "question":
                answer = action.get("args", {}).get("answer", "")
                is_correct = answer.lower() == event["answer"].lower()
                info["correct"] = is_correct
                comp = event["competency"]
                self._by_competency.setdefault(comp, []).append(is_correct)
                self._event_idx += 1
        elif tool == "next":
            self._event_idx += 1

        done = self._event_idx >= len(self._stream)
        if done:
            obs = "Episode complete."
        else:
            e = self._stream[self._event_idx]
            etype = e["type"].upper()
            obs = f"=== Event {self._event_idx + 1}/{len(self._stream)} [{etype}] ==="

        return obs, 0.0, done, info

    def get_verifiable_reward(self):
        scores = compute_axis_scores(
            by_competency=self._by_competency,
            n_entities=self.n_entities,
            stored_count=len(self._stored_entity_names),
            writes_used=self._writes_used,
            write_budget=self.write_budget,
        )
        return scores["composite"]

    def close(self):
        pass


def _patch_env(monkeypatch, fake_env=None):
    """Set up monkeypatches for MemoryGymEnv without heavy deps."""
    if fake_env is None:
        fake_env = _FakeMemoryEnv()

    class _CommonModule:
        @staticmethod
        def get_system_prompt(budget):
            return f"SYSTEM budget={budget}"

        @staticmethod
        def format_tool_result(action, info):
            tool = action["tool"]
            if tool in ("Write", "memory_store"):
                mid = info.get("memory_id", "")
                remaining = info.get("remaining", "?")
                return f"[{tool}] Stored (id={mid}). Budget remaining: {remaining}"
            if tool == "memory_search":
                results = info.get("results", [])
                return f"[memory_search] {len(results)} result(s)"
            return f"[{tool}] done"

    class _TrainingModule:
        @staticmethod
        def MemoryEnv(**kwargs):
            fake_env.kwargs = kwargs
            return fake_env

    monkeypatch.setitem(sys.modules, "memorygym.adapters._common", _CommonModule)
    monkeypatch.setitem(sys.modules, "memorygym.training", _TrainingModule)
    return fake_env


# ---------------------------------------------------------------------------
# Tests: Tier Alignment
# ---------------------------------------------------------------------------


class TestTierAlignment:

    def test_env_default_tier_is_standard(self):
        env = MemoryGymEnv(env_config={})
        assert env._defaults["tier"] == "standard"

    def test_env_defaults_function(self):
        defaults = _env_defaults({})
        assert defaults["tier"] == "standard"

    def test_tier_override_wins_over_row_config(self, monkeypatch):
        fake = _patch_env(monkeypatch)
        env = MemoryGymEnv(env_config={"tier_override": "hard"})
        request = FakeInferRequest(data_dict={"env_config": {"tier": "lite", "seed": 0}})
        obs, info, sys_msg = asyncio.run(env.reset(request))
        assert info["tier"] == "hard"
        assert fake.kwargs["tier"] == "hard"

    def test_standard_tier_parameters(self):
        tier = TIERS["standard"]
        assert tier["entities"] == 60
        assert tier["questions"] == 20
        assert tier["corrections"] == 5
        assert tier["write_budget"] == 30


# ---------------------------------------------------------------------------
# Tests: Thinking Strip
# ---------------------------------------------------------------------------


class TestThinkingStrip:

    def test_strip_think_with_tool_call(self):
        text = (
            '<think>\nLet me think carefully.\n</think>\n'
            '<tool_call>{"name": "Write", "arguments": {"content": "Alice: CEO"}}</tool_call>'
        )
        cleaned = _THINK_RE.sub("", text)
        calls = parse_tool_calls(cleaned)
        assert len(calls) == 1
        assert calls[0]["tool"] == "Write"

    def test_strip_think_preserves_no_think_text(self):
        text = '<tool_call>{"name": "submit_answer", "arguments": {"answer": "42"}}</tool_call>'
        assert _THINK_RE.sub("", text) == text

    def test_truncated_think_no_closing_tag(self):
        text = "<think>\nLong reasoning..."
        assert _THINK_RE.sub("", text) == text

    def test_multiline_think_stripped(self):
        text = "<think>\nLine 1\nLine 2\n</think>\n<tool_call>{}</tool_call>"
        cleaned = _THINK_RE.sub("", text)
        assert "<think>" not in cleaned
        assert "tool_call" in cleaned


# ---------------------------------------------------------------------------
# Tests: JSON Recovery
# ---------------------------------------------------------------------------


class TestJsonRecovery:

    def test_valid_json(self):
        assert _try_parse_json('{"name": "Write"}') == {"name": "Write"}

    def test_missing_one_brace(self):
        r = _try_parse_json('{"name": "Write", "arguments": {"content": "test"}')
        assert r is not None and r["name"] == "Write"

    def test_missing_two_braces(self):
        r = _try_parse_json('{"name": "Write", "arguments": {"content": "test"')
        assert r is not None

    def test_totally_broken(self):
        assert _try_parse_json("broken json {{") is None


# ---------------------------------------------------------------------------
# Tests: Tool Result Feedback
# ---------------------------------------------------------------------------


class TestToolResultFeedback:

    def test_write_returns_tool_result(self, monkeypatch):
        fake = _patch_env(monkeypatch)
        env = MemoryGymEnv(env_config={"tier": "standard"})
        request = FakeInferRequest(data_dict={"env_config": {"seed": SEED}})
        obs, info, sys_msg = asyncio.run(env.reset(request))

        monkeypatch.setattr(
            "orbit_env_memorygym.swift_plugin.parse_memorygym_action",
            lambda text: {"tool": "Write", "args": {"content": "Alice: CEO"}},
        )
        messages = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": obs},
            {"role": "assistant", "content": "..."},
        ]
        next_obs, reward, done, telemetry = asyncio.run(env.step(messages))
        assert "[Write]" in next_obs
        assert "Stored" in next_obs
        assert not done

    def test_next_returns_event_obs_with_summary(self, monkeypatch):
        fake = _patch_env(monkeypatch)
        env = MemoryGymEnv(env_config={"tier": "standard"})
        request = FakeInferRequest(data_dict={"env_config": {"seed": SEED}})
        obs, info, sys_msg = asyncio.run(env.reset(request))

        monkeypatch.setattr(
            "orbit_env_memorygym.swift_plugin.parse_memorygym_action",
            lambda text: {"tool": "next", "args": {}},
        )
        messages = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": obs},
            {"role": "assistant", "content": "..."},
        ]
        next_obs, reward, done, telemetry = asyncio.run(env.step(messages))
        assert "Budget:" in next_obs
        assert "=== Event" in next_obs

    def test_submit_at_done_returns_episode_complete(self, monkeypatch):
        fake = _patch_env(monkeypatch)
        env = MemoryGymEnv(env_config={"tier": "standard"})
        request = FakeInferRequest(data_dict={"env_config": {"seed": SEED}})
        asyncio.run(env.reset(request))
        fake._event_idx = 3  # last event (set after reset)

        monkeypatch.setattr(
            "orbit_env_memorygym.swift_plugin.parse_memorygym_action",
            lambda text: {"tool": "submit_answer", "args": {"answer": "He quit"}},
        )
        messages = [{"role": "assistant", "content": "..."}]
        next_obs, reward, done, telemetry = asyncio.run(env.step(messages))
        assert done is True
        assert next_obs == "Episode complete."
        assert reward > 0.0  # correct answer → non-zero reward


# ---------------------------------------------------------------------------
# Tests: Context Redaction
# ---------------------------------------------------------------------------


class TestContextRedaction:

    def test_redact_at_event_boundary(self):
        ctx = MemoryGymRedactContext({})
        history = [
            {"role": "system", "content": "You are..."},
            {"role": "user", "content": "=== Event 1/50 [DOCUMENTS] ===\n..."},
            {"role": "assistant", "content": "wrote something"},
            {"role": "user", "content": "[Write] Stored."},
            {"role": "assistant", "content": "next"},
            {"role": "user", "content": "=== Event 2/50 [DOCUMENTS] ===\nNew data..."},
        ]
        result = ctx.manage_context(history, "test-id")
        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert "Event 2/50" in result[1]["content"]

    def test_keep_messages_within_event(self):
        ctx = MemoryGymRedactContext({})
        history = [
            {"role": "system", "content": "You are..."},
            {"role": "user", "content": "=== Event 3/50 [QUESTION] ===\nWhat..."},
            {"role": "assistant", "content": "search"},
            {"role": "user", "content": "[memory_search] 1 result"},
        ]
        result = ctx.manage_context(history, "test-id")
        assert len(result) == 4

    def test_episode_complete_triggers_redaction(self):
        ctx = MemoryGymRedactContext({})
        history = [
            {"role": "system", "content": "You are..."},
            {"role": "user", "content": "=== Event 50/50 ..."},
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "Episode complete."},
        ]
        result = ctx.manage_context(history, "test-id")
        assert len(result) == 2
        assert result[1]["content"] == "Episode complete."

    def test_passthrough_preserves_all(self):
        ctx = MemoryGymPassthroughContext({})
        h = [{"role": "system"}, {"role": "user"}, {"role": "assistant"}]
        assert len(ctx.manage_context(h, "t")) == 3

    def test_short_history_unchanged(self):
        ctx = MemoryGymRedactContext({})
        h = [{"role": "system", "content": "sys"}]
        assert ctx.manage_context(h, "t") == h


# ---------------------------------------------------------------------------
# Tests: Scoring Alignment
# ---------------------------------------------------------------------------


class TestScoringAlignment:

    def test_composite_formula(self):
        scores = compute_axis_scores(
            by_competency={"retrieval": [True, True, False]},
            n_entities=60, stored_count=30,
            writes_used=10, write_budget=30,
        )
        expected = (0.30 * scores["breadth"] + 0.25 * scores["maintenance"]
                    + 0.25 * scores["reasoning"] + 0.20 * scores["efficiency"])
        assert abs(scores["composite"] - expected) < 1e-4

    def test_composite_weights_sum_to_one(self):
        assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

    def test_system_prompt_includes_correct_budget(self, monkeypatch):
        """Verify that reset() passes write_budget to get_system_prompt."""
        fake = _patch_env(monkeypatch)
        env = MemoryGymEnv(env_config={"tier": "standard"})
        request = FakeInferRequest(data_dict={"env_config": {"seed": SEED}})
        obs, info, sys_msg = asyncio.run(env.reset(request))
        # The mock get_system_prompt returns "SYSTEM budget=<N>"
        assert sys_msg == f"SYSTEM budget={fake.write_budget}"

    def test_training_reward_matches_direct_compute(self):
        fake = _FakeMemoryEnv()
        fake.reset()
        fake._stored_entity_names = {"Alice"}
        fake._writes_used = 1
        fake._by_competency = {"retrieval": [True, False]}
        training = fake.get_verifiable_reward()
        direct = compute_axis_scores(
            by_competency={"retrieval": [True, False]},
            n_entities=60, stored_count=1,
            writes_used=1, write_budget=30,
        )
        assert abs(training - direct["composite"]) < 1e-6

    def test_nonzero_reward_with_correct_answers(self):
        fake = _FakeMemoryEnv()
        fake.reset()
        fake._stored_entity_names = {"Alice", "Bob"}
        fake._writes_used = 2
        fake._by_competency = {"retrieval": [True]}
        assert fake.get_verifiable_reward() > 0.0


# ---------------------------------------------------------------------------
# Tests: Registration
# ---------------------------------------------------------------------------


class TestPluginRegistration:

    def test_redact_context_registered(self):
        from orbit_env_memorygym.swift_plugin import register_ms_swift_plugin, context_managers
        register_ms_swift_plugin()
        assert "memorygym_redact" in context_managers
        assert "memorygym_passthrough" in context_managers
