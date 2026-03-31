"""Replay-facing entrypoints for GAME self-play generation."""

from forge.data.game_policy_models.selfplay import build_selfplay_replay

__all__ = [
    "build_selfplay_replay",
]
