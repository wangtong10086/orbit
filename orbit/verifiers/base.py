"""Verifier interfaces for task-source evaluation workflows."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import Field

from orbit.foundation.schema import FrozenModel, JsonValue, StrictModel


class VerifierSpec(StrictModel):
    kind: str = "static_trace"
    step_scoring: bool = True
    terminal_scoring: bool = True
    gamma: float = 0.99
    lambda_delta: float = 1.0
    lambda_g: float = 1.0
    lambda_env: float = 1.0
    lambda_u: float = 1.0
    process_weight_scale: float = 1.0
    process_weight_max: float = 4.0
    baseline_strategy: str = "trajectory_mean"
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class VerifierResult(FrozenModel):
    terminal_score: float
    success: bool
    near_miss: bool
    first_error_index: int = -1
    switch_step: int = 0
    potentials: tuple[float, ...] = ()
    local_scores: tuple[float, ...] = ()
    env_rewards: tuple[float, ...] = ()
    process_rewards: tuple[float, ...] = ()
    process_returns: tuple[float, ...] = ()
    process_weights: tuple[float, ...] = ()
    baseline: float = 0.0
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


@runtime_checkable
class Verifier(Protocol):
    spec: VerifierSpec

    def verify(self, trace: dict) -> VerifierResult: ...

    def locate_first_error(self, expected: str, observed: str) -> int: ...

    def state_hash(self, trace: dict) -> str: ...


__all__ = ["Verifier", "VerifierResult", "VerifierSpec"]
