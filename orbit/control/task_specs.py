"""Compatibility re-exports for task specs moved into task plugins."""

from orbit.tasks.collection.specs import (
    CollectPublishConfig,
    CollectTaskSpec,
    GameCollectConfig,
    LivewebCollectConfig,
    MemorygymCollectConfig,
    NavworldCollectConfig,
    SweCollectConfig,
)
from orbit.tasks.evaluation.specs import EvalTaskSpec

__all__ = [
    "CollectPublishConfig",
    "CollectTaskSpec",
    "EvalTaskSpec",
    "GameCollectConfig",
    "LivewebCollectConfig",
    "MemorygymCollectConfig",
    "NavworldCollectConfig",
    "SweCollectConfig",
]
