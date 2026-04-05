"""GEM protocol — standardized environment interaction interface.

Analogous to ROCK's GEM compatibility layer. Provides the standard
reinforcement learning environment interface: make() → reset() → step() → close().

This is the environment interaction layer — separated from the Sandbox API
which handles infrastructure/runtime concerns.

Usage:
    env = default_environment_catalog().make_gem("GAME")
    obs, info = env.reset(seed=42)
    while True:
        obs, reward, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            break
    env.close()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from orbit.env.base import EnvSpec
from orbit.foundation.schema import JsonValue


@dataclass
class Observation:
    """Environment observation returned by reset() and step().

    Encapsulates what the agent can see after each interaction.
    """
    text: str
    metadata: dict[str, JsonValue] = field(default_factory=dict)


@dataclass
class StepResult:
    """Result of env.step(action) — follows GEM/Gymnasium convention.

    Returns (observation, reward, terminated, truncated, info) as a structured object.
    """
    observation: Observation
    reward: float = 0.0
    terminated: bool = False
    truncated: bool = False
    info: dict[str, JsonValue] = field(default_factory=dict)

    def as_tuple(self) -> tuple[Observation, float, bool, bool, dict[str, JsonValue]]:
        """Unpack to standard (obs, reward, terminated, truncated, info) tuple."""
        return (self.observation, self.reward, self.terminated, self.truncated, self.info)


class GemEnv:
    """GEM environment protocol — standard RL interaction interface.

    Analogous to ROCK's GEM protocol support. Every interactive environment
    implements reset/step/close following the Gymnasium convention.

    Subclasses should override reset(), step(), and close().
    The spec attribute provides environment metadata.
    """

    spec: EnvSpec

    def reset(self, seed: int = 42) -> tuple[Observation, dict[str, JsonValue]]:
        """Reset environment and return initial observation.

        Args:
            seed: Random seed for reproducibility.

        Returns:
            (observation, info) tuple.
        """
        raise NotImplementedError(f"{self.__class__.__name__}.reset() not implemented")

    def step(self, action: str) -> StepResult:
        """Execute an action and return the result.

        Args:
            action: The agent's action (typically a text response).

        Returns:
            StepResult with observation, reward, terminated, truncated, info.
        """
        raise NotImplementedError(f"{self.__class__.__name__}.step() not implemented")

    def close(self) -> None:
        """Clean up environment resources.

        Override for environments that hold external resources
        (sandbox connections, file handles, etc.).
        """
        pass

    @property
    def is_interactive(self) -> bool:
        """Whether this env supports real-time interaction (vs offline data only)."""
        return False
