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
    feature_shape: list[int] = []


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


def _symbol_for_player(player_id: int) -> str:
    return "x" if int(player_id) == 0 else "o"


def _parse_board_tokens(state, *, expected_rows: int, expected_cols: int) -> list[list[str]]:
    rows: list[list[str]] = []
    for raw_line in state.observation_string(state.current_player() if state.current_player() >= 0 else 0).splitlines():
        cells = []
        for char in raw_line:
            if char in {"x", "o"}:
                cells.append(char)
            elif char in {".", "-"}:
                cells.append(".")
        if len(cells) == expected_cols:
            rows.append(cells)
    if len(rows) != expected_rows:
        raise RuntimeError(f"Unable to parse board rows from {type(state).__name__}: expected {expected_rows}, got {len(rows)}")
    return rows


def _board_occupancy_planes(board: list[list[str]], *, player_id: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    height = len(board)
    width = len(board[0]) if board else 0
    own = np.zeros((height, width), dtype=np.float32)
    opp = np.zeros((height, width), dtype=np.float32)
    empty = np.zeros((height, width), dtype=np.float32)
    own_char = _symbol_for_player(player_id)
    opp_char = _symbol_for_player(1 - int(player_id))
    for row_index, row in enumerate(board):
        for col_index, cell in enumerate(row):
            if cell == own_char:
                own[row_index, col_index] = 1.0
            elif cell == opp_char:
                opp[row_index, col_index] = 1.0
            else:
                empty[row_index, col_index] = 1.0
    return own, opp, empty


def _coord_from_action_string(action_string: str) -> tuple[int, int]:
    column = ord(action_string[0].lower()) - ord("a")
    row = int(action_string[1:]) - 1
    return row, column


def _othello_planes(state, player_id: int) -> np.ndarray:
    board = _parse_board_tokens(state, expected_rows=8, expected_cols=8)
    own, opp, empty = _board_occupancy_planes(board, player_id=player_id)
    legal = np.zeros((8, 8), dtype=np.float32)
    for action in state.legal_actions(player_id):
        action_string = state.action_to_string(player_id, action)
        if len(action_string) < 2 or action_string == "pass":
            continue
        row, col = _coord_from_action_string(action_string)
        if 0 <= row < 8 and 0 <= col < 8:
            legal[row, col] = 1.0
    turn = np.full((8, 8), 1.0 if int(player_id) == 0 else 0.0, dtype=np.float32)
    corners = np.zeros((8, 8), dtype=np.float32)
    for row, col in ((0, 0), (0, 7), (7, 0), (7, 7)):
        corners[row, col] = 1.0
    return np.stack([own, opp, legal, turn, empty, corners], axis=0)


def _hex_planes(state, player_id: int, *, board_size: int = 7, padded_size: int = 11) -> np.ndarray:
    board = _parse_board_tokens(state, expected_rows=board_size, expected_cols=board_size)
    own_small, opp_small, _ = _board_occupancy_planes(board, player_id=player_id)
    own = np.zeros((padded_size, padded_size), dtype=np.float32)
    opp = np.zeros((padded_size, padded_size), dtype=np.float32)
    own[:board_size, :board_size] = own_small
    opp[:board_size, :board_size] = opp_small
    legal = np.zeros((padded_size, padded_size), dtype=np.float32)
    for action in state.legal_actions(player_id):
        action_string = state.action_to_string(player_id, action)
        if len(action_string) < 2:
            continue
        row, col = _coord_from_action_string(action_string)
        if 0 <= row < board_size and 0 <= col < board_size:
            legal[row, col] = 1.0
    turn = np.full((padded_size, padded_size), 1.0 if int(player_id) == 0 else 0.0, dtype=np.float32)
    edge_a = np.zeros((padded_size, padded_size), dtype=np.float32)
    edge_b = np.zeros((padded_size, padded_size), dtype=np.float32)
    if int(player_id) == 0:
        edge_a[0, :board_size] = 1.0
        edge_b[board_size - 1, :board_size] = 1.0
    else:
        edge_a[:board_size, 0] = 1.0
        edge_b[:board_size, board_size - 1] = 1.0
    board_mask = np.zeros((padded_size, padded_size), dtype=np.float32)
    board_mask[:board_size, :board_size] = 1.0
    return np.stack([own, opp, legal, turn, edge_a, edge_b, board_mask], axis=0)


def _clobber_planes(state, player_id: int, *, board_size: int = 5, padded_size: int = 7) -> np.ndarray:
    board = _parse_board_tokens(state, expected_rows=board_size, expected_cols=board_size)
    own_small, opp_small, empty_small = _board_occupancy_planes(board, player_id=player_id)
    own = np.zeros((padded_size, padded_size), dtype=np.float32)
    opp = np.zeros((padded_size, padded_size), dtype=np.float32)
    empty = np.zeros((padded_size, padded_size), dtype=np.float32)
    own[:board_size, :board_size] = own_small
    opp[:board_size, :board_size] = opp_small
    empty[:board_size, :board_size] = empty_small
    legal_origin = np.zeros((padded_size, padded_size), dtype=np.float32)
    legal_target = np.zeros((padded_size, padded_size), dtype=np.float32)
    for action in state.legal_actions(player_id):
        action_string = state.action_to_string(player_id, action)
        if len(action_string) < 4:
            continue
        origin_row, origin_col = _coord_from_action_string(action_string[:2])
        target_row, target_col = _coord_from_action_string(action_string[2:])
        if 0 <= origin_row < board_size and 0 <= origin_col < board_size:
            legal_origin[origin_row, origin_col] = 1.0
        if 0 <= target_row < board_size and 0 <= target_col < board_size:
            legal_target[target_row, target_col] = 1.0
    turn = np.full((padded_size, padded_size), 1.0 if int(player_id) == 0 else 0.0, dtype=np.float32)
    board_mask = np.zeros((padded_size, padded_size), dtype=np.float32)
    board_mask[:board_size, :board_size] = 1.0
    return np.stack([own, opp, empty, legal_origin, legal_target, turn, board_mask], axis=0)


def _perfect_info_tensor(state, player_id: int) -> np.ndarray:
    game_name = str(state.get_game().get_type().short_name)
    if game_name == "othello":
        return _othello_planes(state, player_id).reshape(-1)
    if game_name == "hex":
        return _hex_planes(state, player_id).reshape(-1)
    if game_name == "clobber":
        return _clobber_planes(state, player_id).reshape(-1)
    raise KeyError(game_name)


def extract_state_features(state, player_id: int) -> np.ndarray:
    """Return a structured feature vector for a player at the current state."""
    game_name = ""
    try:
        game_name = str(state.get_game().get_type().short_name)
    except Exception:
        game_name = ""
    if game_name in {"othello", "hex", "clobber"}:
        return _perfect_info_tensor(state, player_id)
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
    feature_shape = [int(features.shape[0])]
    source = "observation_tensor"
    if game_name == "othello":
        feature_shape = [6, 8, 8]
        source = "board_planes"
    elif game_name == "hex":
        feature_shape = [7, 11, 11]
        source = "board_planes"
    elif game_name == "clobber":
        feature_shape = [7, 7, 7]
        source = "board_planes"
    return GameFeatureSpec(
        game=game_name,
        input_dim=int(features.shape[0]),
        action_dim=int(state.get_game().num_distinct_actions()),
        source=source,
        feature_shape=feature_shape,
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
        source="board_planes" if game_name in {"othello", "hex", "clobber"} else "observation_tensor",
        feature_shape=[6, 8, 8]
        if game_name == "othello"
        else [7, 11, 11]
        if game_name == "hex"
        else [7, 7, 7]
        if game_name == "clobber"
        else [int(features.shape[0])],
    )


def ensure_parent(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target
