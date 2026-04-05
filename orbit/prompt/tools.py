"""Tool schema management — load and compose tool definitions.

Provides helpers for loading tool schemas from JSON templates
and converting between formats.
"""

from __future__ import annotations

import json
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent / "templates"


def load_tools(env_name: str, file_name: str = "tools") -> list[dict]:
    """Load tool definitions from templates/{env_name}/{file_name}.json."""
    path = TEMPLATES_DIR / env_name / f"{file_name}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return []


def tool_names(env_name: str) -> list[str]:
    """Return the names of all tools for an environment."""
    tools = load_tools(env_name)
    return [t["function"]["name"] for t in tools if "function" in t]


def get_tool_schema(env_name: str, tool_name: str) -> dict | None:
    """Get a single tool schema by name."""
    for t in load_tools(env_name):
        if t.get("function", {}).get("name") == tool_name:
            return t
    return None
