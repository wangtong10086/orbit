"""Trainer-facing entrypoints for GAME self-play."""

from forge.data.game_policy_models.selfplay import (
    resume_selfplay_policy_model,
    train_selfplay_policy_model,
    train_selfplay_until_gate,
)

__all__ = [
    "resume_selfplay_policy_model",
    "train_selfplay_policy_model",
    "train_selfplay_until_gate",
]
