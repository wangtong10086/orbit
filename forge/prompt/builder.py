"""Prompt builder — composable message sequence construction.

Loads templates from forge/prompt/templates/{env}/ directory.
Supports system/user/assistant/tool messages with variable substitution.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass
class Message:
    """A single message in a conversation."""

    role: str
    content: str
    tool_calls: Optional[list] = None
    tool_call_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to OpenAI-compatible dict format."""
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls is not None:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id
        return d


class PromptBuilder:
    """Build message sequences from templates and programmatic additions.

    Usage:
        pb = PromptBuilder("navworld")
        pb.system("system")          # loads templates/navworld/system.md
        pb.user("Plan a trip to Shanghai")
        pb.assistant("Let me search...")
        msgs = pb.build()            # -> list[dict]
    """

    def __init__(self, env_name: str):
        self.env_name = env_name.lower()
        self._messages: list[Message] = []

    def system(self, template_name: str = "system", **kwargs) -> "PromptBuilder":
        """Add system message from template file or raw text.

        Looks for templates/{env_name}/{template_name}.md first.
        If not found, uses template_name as literal content.
        """
        content = self._load_template(template_name, **kwargs)
        self._messages.append(Message(role="system", content=content))
        return self

    def user(self, content: str) -> "PromptBuilder":
        """Add user message."""
        self._messages.append(Message(role="user", content=content))
        return self

    def assistant(self, content: str, tool_calls: Optional[list] = None) -> "PromptBuilder":
        """Add assistant message, optionally with tool calls."""
        self._messages.append(Message(role="assistant", content=content, tool_calls=tool_calls))
        return self

    def tool(self, content: str, tool_call_id: str) -> "PromptBuilder":
        """Add tool result message."""
        self._messages.append(Message(role="tool", content=content, tool_call_id=tool_call_id))
        return self

    def add_message(self, role: str, content: str, **kwargs) -> "PromptBuilder":
        """Add an arbitrary message."""
        self._messages.append(Message(role=role, content=content, **kwargs))
        return self

    def build(self) -> list[dict]:
        """Build the final message list in OpenAI format."""
        return [m.to_dict() for m in self._messages]

    def clear(self) -> "PromptBuilder":
        """Reset the builder."""
        self._messages = []
        return self

    @classmethod
    def from_messages(cls, env_name: str, messages: list[dict]) -> "PromptBuilder":
        """Create a builder from an existing message list."""
        pb = cls(env_name)
        for msg in messages:
            pb._messages.append(Message(
                role=msg["role"],
                content=msg.get("content", ""),
                tool_calls=msg.get("tool_calls"),
                tool_call_id=msg.get("tool_call_id"),
            ))
        return pb

    def load_tools(self, tools_file: str = "tools") -> list[dict]:
        """Load tool definitions from a JSON template file.

        Returns list of tool definitions in OpenAI format.
        """
        path = TEMPLATES_DIR / self.env_name / f"{tools_file}.json"
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return []

    def _load_template(self, name: str, **kwargs) -> str:
        """Load a template file and substitute variables."""
        path = TEMPLATES_DIR / self.env_name / f"{name}.md"
        if path.exists():
            content = path.read_text()
            for key, value in kwargs.items():
                content = content.replace(f"{{{{{key}}}}}", str(value))
            return content
        # Fallback: treat name as literal content
        return name
