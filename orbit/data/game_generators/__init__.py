"""Modular GAME trajectory generators.

Keep this package import-light so CLI help in minimal installs does not pull in
optional OpenSpiel/numpy dependencies at import time.
"""

from orbit.data.game_generators.base import (
    GameTrajectoryGenerator,
    GameTrajectoryGeneratorReport,
    PolicyBuildReport,
    PolicyStatusEntry,
)

__all__ = [
    "GameTrajectoryGenerator",
    "GameTrajectoryGeneratorReport",
    "PolicyBuildReport",
    "PolicyStatusEntry",
]
