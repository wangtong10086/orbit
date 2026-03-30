"""Structured GAME feature extraction from OpenSpiel state tensors."""

from __future__ import annotations

from pathlib import Path
import zlib

import numpy as np

from forge.foundation.schema import FrozenModel


STRING_FALLBACK_DIM = 256


class GameFeatureSpec(FrozenModel):
    game: str
    input_dim: int
    action_dim: int
    source: str = "observation_tensor"


def _state_tensor(state, player_id: int) -> np.ndarray:
    game_name = ""
    try:
        game_name = str(state.get_game().get_type().short_name)
    except Exception:
        game_name = ""
    if game_name == "gin_rummy":
        primary_attrs = ("information_state_string", "observation_string", "serialize")
        fallback_attrs = ("information_state_tensor", "observation_tensor")
    else:
        primary_attrs = ("information_state_tensor", "observation_tensor")
        fallback_attrs = ("information_state_string", "observation_string", "serialize")

    for attr_group in (primary_attrs, fallback_attrs):
        for attr in attr_group:
            fn = getattr(state, attr, None)
            if fn is None:
                continue
            try:
                value = fn(player_id)
            except TypeError:
                try:
                    value = fn()
                except Exception:
                    continue
            except Exception:
                continue
            if attr.endswith("_tensor"):
                try:
                    array = np.asarray(value, dtype=np.float32).reshape(-1)
                except Exception:
                    continue
                if array.size:
                    return array
                continue
            if not value:
                continue
            text = str(value)
            vector = np.zeros(STRING_FALLBACK_DIM, dtype=np.float32)
            for token in text.replace("\n", " ").split():
                vector[zlib.adler32(token.encode("utf-8")) % STRING_FALLBACK_DIM] += 1.0
            if vector.sum() > 0:
                vector /= float(vector.sum())
                return vector
    raise RuntimeError(f"{type(state).__name__} does not expose a usable tensor observation")


def extract_state_features(state, player_id: int) -> np.ndarray:
    """Return a structured feature vector for a player at the current state."""

    return _state_tensor(state, player_id)


def legal_action_mask(game, state, player_id: int) -> np.ndarray:
    """Return a dense legal-action mask sized to the game's action space."""

    action_dim = int(game.num_distinct_actions())
    mask = np.zeros(action_dim, dtype=np.float32)
    for action in state.legal_actions(player_id):
        if 0 <= action < action_dim:
            mask[action] = 1.0
    return mask


def feature_spec_for_state(game_name: str, state, player_id: int) -> GameFeatureSpec:
    features = extract_state_features(state, player_id)
    return GameFeatureSpec(
        game=game_name,
        input_dim=int(features.shape[0]),
        action_dim=int(state.get_game().num_distinct_actions()),
    )


def feature_spec_for_game(game_name: str, params: dict[str, object] | None = None) -> GameFeatureSpec:
    import pyspiel

    game = pyspiel.load_game(game_name, params or {})
    state = game.new_initial_state()
    player_id = 0 if game.num_players() else 0
    features = extract_state_features(state, player_id)
    return GameFeatureSpec(
        game=game_name,
        input_dim=int(features.shape[0]),
        action_dim=int(game.num_distinct_actions()),
    )


def ensure_parent(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target
