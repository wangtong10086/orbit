"""Agent base protocol — interface for all autonomous agents."""

from __future__ import annotations

from typing import Protocol

from pydantic import Field

from forge.foundation.schema import FrozenModel, JsonValue


class AgentState(FrozenModel):
    """Structured state snapshot consumed by agent planning."""

    data: dict[str, JsonValue] = Field(default_factory=dict)


class AgentPlan(FrozenModel):
    """Structured action proposal emitted by agent planning."""

    action: str
    params: dict[str, JsonValue] = Field(default_factory=dict)


class StepResult(FrozenModel):
    """Structured result of a single agent step."""

    action: str
    success: bool
    details: dict[str, JsonValue] = Field(default_factory=dict)


class AgentProtocol(Protocol):
    """Base protocol for autonomous agents.

    All agents follow a sense → plan → act → reflect cycle.
    """

    def sense(self) -> AgentState:
        """Gather current state (leaderboard, experiment history, data status)."""
        ...

    def plan(self, state: AgentState) -> AgentPlan:
        """Decide what to do next based on current state."""
        ...

    def act(self, plan: AgentPlan) -> StepResult:
        """Execute the planned action."""
        ...

    def reflect(self, result: StepResult) -> None:
        """Learn from the result and update internal state."""
        ...


__all__ = ["AgentPlan", "AgentProtocol", "AgentState", "StepResult"]
