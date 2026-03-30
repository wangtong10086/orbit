"""Configurable GAME trajectory-generator registry.

The collection pipeline should not hard-code one script for every game.
This module provides a small, explicit registry so we can swap trajectory
generators per game without rewriting the collector.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from forge.foundation.schema import FrozenModel


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RANDOM_SCRIPT = PROJECT_ROOT / "scripts" / "game" / "generate_random.py"


class GameTrajectoryGeneratorSpec(FrozenModel):
    name: str
    script_path: str
    env: dict[str, str] = Field(default_factory=dict)


def resolve_game_trajectory_generator(game_name: str) -> GameTrajectoryGeneratorSpec:
    """Return the active trajectory-generator spec for a GAME environment."""

    # Current policy: use the random generator for every game until
    # game-specific generators are reintroduced one by one.
    return GameTrajectoryGeneratorSpec(
        name="random",
        script_path=str(DEFAULT_RANDOM_SCRIPT),
    )
