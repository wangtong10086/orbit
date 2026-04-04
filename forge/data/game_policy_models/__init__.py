"""Small per-game policy models — teacher inference for GAME trajectory sampling."""

from __future__ import annotations

from forge.data.game_policy_models.inference import (
    PolicyModelStatusEntry,
    default_policy_model_dir,
    play_record,
    policy_model_status,
    resolve_policy_model_dir,
    select_policy_model_action,
)
from forge.data.game_policy_models.models import (
    PolicyModelArtifact,
    PolicyModelTrainReport,
    default_selfplay_model_config,
    load_policy_model,
    train_policy_model,
)

__all__ = [
    "PolicyModelArtifact",
    "PolicyModelStatusEntry",
    "PolicyModelTrainReport",
    "default_policy_model_dir",
    "default_selfplay_model_config",
    "load_policy_model",
    "play_record",
    "policy_model_status",
    "resolve_policy_model_dir",
    "select_policy_model_action",
    "train_policy_model",
]


def build_expert_dataset(**kwargs):
    raise NotImplementedError("build_expert_dataset is not implemented in this trimmed checkout")


def train_selfplay_policy_model(**kwargs):
    raise NotImplementedError("train_selfplay_policy_model is not implemented in this trimmed checkout")


def selfplay_status(**kwargs):
    raise NotImplementedError("selfplay_status is not implemented in this trimmed checkout")


def evaluate_selfplay_policy_model(**kwargs):
    raise NotImplementedError("evaluate_selfplay_policy_model is not implemented in this trimmed checkout")


def resume_selfplay_policy_model(**kwargs):
    raise NotImplementedError("resume_selfplay_policy_model is not implemented in this trimmed checkout")


__all__.extend(
    [
        "build_expert_dataset",
        "train_selfplay_policy_model",
        "selfplay_status",
        "evaluate_selfplay_policy_model",
        "resume_selfplay_policy_model",
    ]
)
