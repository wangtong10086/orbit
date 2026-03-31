"""Arena-facing entrypoints for GAME self-play evaluation."""

from forge.data.game_policy_models.selfplay import evaluate_selfplay_policy_model, selfplay_record

__all__ = [
    "evaluate_selfplay_policy_model",
    "selfplay_record",
]
