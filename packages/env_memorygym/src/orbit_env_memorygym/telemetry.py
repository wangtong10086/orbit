"""Telemetry helpers for the MemoryGym environment pack."""

from __future__ import annotations

from typing import Any


def build_memorygym_telemetry(
    *,
    info: dict[str, Any] | None,
    parsed_action: dict[str, Any],
    done: bool,
    template_name: str = "",
    tier: str = "",
    seed: int = 0,
) -> dict[str, Any]:
    telemetry = dict(info or {})
    telemetry["parsed_action"] = parsed_action
    telemetry["terminated"] = bool(done)
    if template_name and "template" not in telemetry:
        telemetry["template"] = template_name
    if tier and "tier" not in telemetry:
        telemetry["tier"] = tier
    if seed and "seed" not in telemetry:
        telemetry["seed"] = int(seed)
    return telemetry


__all__ = ["build_memorygym_telemetry"]
