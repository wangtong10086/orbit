"""Agent base protocol — interface for all autonomous agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class StepResult:
    """Result of a single agent step."""

    action: str
    success: bool
    details: dict


class AgentProtocol(Protocol):
    """Base protocol for autonomous agents.

    All agents follow a sense → plan → act → reflect cycle.
    """

    def sense(self) -> dict:
        """Gather current state (leaderboard, experiment history, data status)."""
        ...

    def plan(self, state: dict) -> dict:
        """Decide what to do next based on current state."""
        ...

    def act(self, plan: dict) -> StepResult:
        """Execute the planned action."""
        ...

    def reflect(self, result: StepResult) -> None:
        """Learn from the result and update internal state."""
        ...
