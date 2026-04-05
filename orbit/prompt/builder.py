"""Prompt builder — composable message sequence construction."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field

from orbit.foundation.schema import StrictModel

TEMPLATES_DIR = Path(__file__).parent / "templates"


class TemplateContext(StrictModel):
    variables: dict[str, str | int | float | bool] = Field(default_factory=dict)


class Message(StrictModel):
    """A single message in a conversation."""

    role: str
    content: str
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None

    def to_dict(self) -> dict:
        d = {"role": self.role, "content": self.content}
        if self.tool_calls is not None:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id
        return d


class PromptBuilder:
    """Build message sequences from templates and programmatic additions."""

    def __init__(self, env_name: str):
        self.env_name = env_name.lower()
        self._messages: list[Message] = []

    def system(self, template_name: str = "system", context: TemplateContext | None = None) -> "PromptBuilder":
        content = self._load_template(template_name, context=context)
        self._messages.append(Message(role="system", content=content))
        return self

    def user(self, content: str) -> "PromptBuilder":
        self._messages.append(Message(role="user", content=content))
        return self

    def assistant(self, content: str, tool_calls: list[dict] | None = None) -> "PromptBuilder":
        self._messages.append(Message(role="assistant", content=content, tool_calls=tool_calls))
        return self

    def tool(self, content: str, tool_call_id: str) -> "PromptBuilder":
        self._messages.append(Message(role="tool", content=content, tool_call_id=tool_call_id))
        return self

    def add_message(self, message: Message) -> "PromptBuilder":
        self._messages.append(message)
        return self

    def build(self) -> list[dict]:
        return [m.to_dict() for m in self._messages]

    def clear(self) -> "PromptBuilder":
        self._messages = []
        return self

    @classmethod
    def from_messages(cls, env_name: str, messages: list[dict]) -> "PromptBuilder":
        pb = cls(env_name)
        for msg in messages:
            pb._messages.append(
                Message(
                    role=msg["role"],
                    content=msg.get("content", ""),
                    tool_calls=msg.get("tool_calls"),
                    tool_call_id=msg.get("tool_call_id"),
                )
            )
        return pb

    def load_tools(self, tools_file: str = "tools") -> list[dict]:
        path = TEMPLATES_DIR / self.env_name / f"{tools_file}.json"
        if path.exists():
            with path.open(encoding="utf-8") as handle:
                return json.load(handle)
        return []

    def _load_template(self, name: str, context: TemplateContext | None = None) -> str:
        path = TEMPLATES_DIR / self.env_name / f"{name}.md"
        if path.exists():
            content = path.read_text(encoding="utf-8")
            for key, value in (context.variables if context else {}).items():
                content = content.replace(f"{{{{{key}}}}}", str(value))
            return content
        return name
