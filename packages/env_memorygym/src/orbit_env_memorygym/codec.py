"""Action codec for the MemoryGym environment pack."""

from __future__ import annotations

from typing import Any


def parse_memorygym_action(assistant_text: str) -> dict[str, Any]:
    from memorygym.adapters._common import parse_tool_calls

    parsed_calls = parse_tool_calls(assistant_text or "")
    return dict(parsed_calls[-1]) if parsed_calls else {"tool": "next"}


__all__ = ["parse_memorygym_action"]
