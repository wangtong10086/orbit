"""Game contracts, task registry, codecs, and OpenSpiel adapters."""

from .action_codecs import ActionCodec, get_action_codec
from .adapters import AffineOpenSpielAdapter, EncodedGameState
from .affine_registry import AffineTaskRegistry, DEFAULT_REGISTRY
from .encoders import GameStateEncoder, build_state_encoder
from .game_spec import GameSpec

__all__ = [
    "ActionCodec",
    "AffineOpenSpielAdapter",
    "AffineTaskRegistry",
    "DEFAULT_REGISTRY",
    "EncodedGameState",
    "GameSpec",
    "GameStateEncoder",
    "build_state_encoder",
    "get_action_codec",
]
