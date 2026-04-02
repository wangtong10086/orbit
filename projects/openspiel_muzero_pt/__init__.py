"""PyTorch MuZero stack for Affine OpenSpiel board games."""

from .games.affine_registry import AffineTaskRegistry, DEFAULT_REGISTRY
from .games.game_spec import GameSpec

__all__ = ["AffineTaskRegistry", "DEFAULT_REGISTRY", "GameSpec"]
