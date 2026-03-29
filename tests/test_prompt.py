"""Tests for Layer 0: forge/prompt — prompt engine and templates."""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge.prompt.builder import Message, PromptBuilder, TemplateContext
from forge.prompt.tools import load_tools, tool_names, get_tool_schema


class TestMessage:
    def test_to_dict_basic(self):
        msg = Message(role="user", content="hello")
        d = msg.to_dict()
        assert d["role"] == "user"
        assert d["content"] == "hello"
        assert "tool_calls" not in d
        assert "tool_call_id" not in d

    def test_to_dict_with_tool_calls(self):
        msg = Message(role="assistant", content="ok", tool_calls=[{"id": "1"}])
        d = msg.to_dict()
        assert d["tool_calls"] == [{"id": "1"}]

    def test_to_dict_with_tool_call_id(self):
        msg = Message(role="tool", content="result", tool_call_id="call_1")
        d = msg.to_dict()
        assert d["tool_call_id"] == "call_1"


class TestPromptBuilder:
    def test_basic_build(self):
        pb = PromptBuilder("game")
        msgs = pb.user("hello").assistant("world").build()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

    def test_env_name_lowercased(self):
        pb = PromptBuilder("GAME")
        assert pb.env_name == "game"

    def test_system_with_template(self):
        pb = PromptBuilder("game")
        pb.system("system", context=TemplateContext(variables={"game_name": "chess"}))
        msgs = pb.build()
        assert len(msgs) == 1
        assert msgs[0]["role"] == "system"
        # Template should contain the game name
        assert "chess" in msgs[0]["content"]

    def test_tool_message(self):
        pb = PromptBuilder("navworld")
        pb.tool("result data", tool_call_id="call_123")
        msgs = pb.build()
        assert msgs[0]["role"] == "tool"
        assert msgs[0]["tool_call_id"] == "call_123"

    def test_clear(self):
        pb = PromptBuilder("game")
        pb.user("hello")
        pb.clear()
        msgs = pb.build()
        assert msgs == []

    def test_from_messages(self):
        raw = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello", "tool_calls": [{"id": "1"}]},
        ]
        pb = PromptBuilder.from_messages("game", raw)
        msgs = pb.build()
        assert len(msgs) == 2
        assert msgs[1]["tool_calls"] == [{"id": "1"}]

    def test_system_literal_fallback(self):
        """If template file doesn't exist, the name is used as literal content."""
        pb = PromptBuilder("game")
        pb.system("nonexistent_template_xyz")
        msgs = pb.build()
        assert msgs[0]["content"] == "nonexistent_template_xyz"

    def test_fluent_chaining(self):
        msgs = (
            PromptBuilder("game")
            .user("q1")
            .assistant("a1")
            .user("q2")
            .assistant("a2")
            .build()
        )
        assert len(msgs) == 4
        assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]

    def test_add_message(self):
        pb = PromptBuilder("game")
        pb.add_message(Message(role="custom_role", content="content"))
        msgs = pb.build()
        assert msgs[0]["role"] == "custom_role"


class TestToolLoading:
    def test_load_navworld_tools(self):
        tools = load_tools("navworld")
        assert len(tools) > 0
        # Each tool should have function schema
        for t in tools:
            assert "function" in t
            assert "name" in t["function"]

    def test_tool_names_navworld(self):
        names = tool_names("navworld")
        expected = {"poi_search", "around_search", "direction", "weather",
                    "search_flights", "search_train_tickets"}
        assert expected == set(names)

    def test_get_tool_schema(self):
        schema = get_tool_schema("navworld", "weather")
        assert schema is not None
        assert schema["function"]["name"] == "weather"

    def test_get_tool_schema_nonexistent(self):
        schema = get_tool_schema("navworld", "nonexistent_tool")
        assert schema is None

    def test_load_tools_unknown_env(self):
        tools = load_tools("nonexistent_env_xyz")
        assert tools == []
