"""Compatibility re-exports for task specs moved into task plugins."""

from forge.tasks.collection.specs import (
    CollectPublishConfig,
    CollectTaskSpec,
    GameCollectConfig,
    LivewebCollectConfig,
    MemorygymCollectConfig,
    NavworldCollectConfig,
    SweCollectConfig,
)
from forge.tasks.evaluation.specs import EvalTaskSpec

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
