"""Compatibility shim for policy-model training entrypoints."""

from forge.data.game_policy_models.models import (
    PolicyModelArtifact,
    PolicyModelTrainReport,
    load_policy_model,
    train_policy_model,
)
from forge.data.game_policy_models.selfplay import (
    ArenaEvalReport,
    SelfPlayTrainReport,
    evaluate_selfplay_policy_model,
    resume_selfplay_policy_model,
    train_selfplay_policy_model,
)

__all__ = [
    "ArenaEvalReport",
    "PolicyModelArtifact",
    "PolicyModelTrainReport",
    "SelfPlayTrainReport",
    "evaluate_selfplay_policy_model",
    "load_policy_model",
    "resume_selfplay_policy_model",
    "train_selfplay_policy_model",
    "train_policy_model",
]
