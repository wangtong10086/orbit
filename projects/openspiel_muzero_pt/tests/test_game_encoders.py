from __future__ import annotations

from projects.openspiel_muzero_pt.games.affine_registry import DEFAULT_REGISTRY
from projects.openspiel_muzero_pt.games.encoders import build_state_encoder


class FakeState:
    def __init__(self, board_text: str, *, current_player: int, terminal: bool = False):
        self._board_text = board_text
        self._current_player = current_player
        self._terminal = terminal

    def is_terminal(self) -> bool:
        return self._terminal

    def current_player(self) -> int:
        return self._current_player

    def observation_string(self, observer: int) -> str:
        return self._board_text


def test_othello_encoder_maps_current_player_to_own_plane():
    spec = DEFAULT_REGISTRY.get_spec(400_000_000)
    encoder = build_state_encoder(spec)
    state = FakeState(
        "\n".join(
            [
                "x.......",
                ".o......",
                "........",
                "........",
                "........",
                "........",
                "........",
                "........",
            ]
        ),
        current_player=1,
    )
    encoded = encoder.encode(state)
    assert encoded.shape == (5, 8, 8)
    assert float(encoded[0, 1, 1]) == 1.0
    assert float(encoded[1, 0, 0]) == 1.0


def test_hex_encoder_transposes_white_to_move_into_black_view():
    spec = DEFAULT_REGISTRY.get_spec(600_000_000)
    encoder = build_state_encoder(spec)
    state = FakeState(
        "\n".join(
            [
                "x....",
                ".o...",
                ".....",
                ".....",
                ".....",
            ]
        ),
        current_player=1,
    )
    encoded = encoder.encode(state)
    assert encoded.shape == (5, 11, 11)
    assert float(encoded[0, 1, 1]) == 1.0
    assert float(encoded[1, 0, 0]) == 1.0
