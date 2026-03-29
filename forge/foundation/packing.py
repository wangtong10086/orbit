"""Conversation packers for training dataset construction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from forge.foundation.contracts import ConversationPacker
from forge.foundation.schema import JsonValue
from forge.prompt.tools import load_tools

_LIVEWEB_TOOLS_PATH = Path(__file__).parents[1] / "data" / "liveweb_tools.json"


def _load_env_tools(env_name: str) -> list[dict[str, JsonValue]]:
    normalized = env_name.lower()
    tools = load_tools(normalized)
    if tools:
        return tools
    if env_name == "LIVEWEB" and _LIVEWEB_TOOLS_PATH.exists():
        with _LIVEWEB_TOOLS_PATH.open(encoding="utf-8") as handle:
            return json.load(handle)
    return []


def _tool_preamble(tools: list[dict[str, JsonValue]]) -> str:
    if not tools:
        return ""
    lines = [
        "",
        "",
        "# Tools",
        "",
        "You may call one or more functions to assist with the user query.",
        "",
        "You are provided with function signatures within <tools></tools> XML tags:",
        "<tools>",
    ]
    lines.extend(json.dumps(tool, ensure_ascii=False) for tool in tools)
    lines.extend(
        [
            "</tools>",
            "",
            'For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:',
            '<tool_call>',
            '{"name": <function-name>, "arguments": <args-json-object>}',
            "</tool_call>",
        ]
    )
    return "\n".join(lines)


class IdentityConversationPacker(ConversationPacker):
    """Minimal packer: keep message roles and content as canonicalized text."""

    def pack(self, record: Mapping[str, JsonValue]) -> list[dict[str, JsonValue]]:
        packed: list[dict[str, JsonValue]] = []
        for message in record.get("messages", []):
            packed.append(
                {
                    "role": message["role"],
                    "content": message.get("content", "") or "",
                }
            )
        return packed


class Qwen3ConversationPacker(ConversationPacker):
    """Pack canonical conversations into the Qwen3 chat-template-compatible form."""

    def __init__(self, default_env_name: str | None = None):
        self.default_env_name = default_env_name

    def pack(self, record: Mapping[str, JsonValue]) -> list[dict[str, JsonValue]]:
        env_name = record.get("env") or self.default_env_name or ""
        tools = _load_env_tools(env_name)
        tool_preamble = _tool_preamble(tools)

        packed: list[dict[str, JsonValue]] = []
        for message in record.get("messages", []):
            role = message["role"]
            content = message.get("content", "") or ""

            if role == "system":
                packed.append({"role": "system", "content": content + tool_preamble})
                continue

            if role == "assistant" and message.get("tool_calls"):
                parts = []
                for tool_call in message["tool_calls"]:
                    fn = tool_call.get("function", {})
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except (json.JSONDecodeError, TypeError):
                            args = {}
                    parts.append(
                        "<tool_call>\n"
                        + json.dumps(
                            {"name": fn.get("name", ""), "arguments": args},
                            ensure_ascii=False,
                        )
                        + "\n</tool_call>"
                    )
                tool_call_text = "\n".join(parts)
                packed.append(
                    {
                        "role": "assistant",
                        "content": (content + "\n" + tool_call_text).strip()
                        if content
                        else tool_call_text,
                    }
                )
                continue

            if role == "tool":
                packed.append(
                    {
                        "role": "user",
                        "content": f"<tool_response>\n{content}\n</tool_response>",
                    }
                )
                continue

            packed.append({"role": role, "content": content})

        return packed
