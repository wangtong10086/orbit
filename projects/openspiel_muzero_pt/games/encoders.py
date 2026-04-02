from __future__ import annotations

from typing import Protocol

import numpy as np

from .game_spec import GameSpec


class GameStateEncoder(Protocol):
    spec: GameSpec

    def encode(self, state) -> np.ndarray: ...


class ObservationStringEncoder:
    def __init__(self, spec: GameSpec):
        self.spec = spec

    def encode(self, state) -> np.ndarray:
        raise NotImplementedError

    def _canonical_current_player(self, state) -> int:
        return 0 if state.is_terminal() else int(state.current_player())

    def _parse_board_tokens(self, state, *, expected_rows: int, expected_cols: int) -> list[list[str]]:
        observer = state.current_player() if not state.is_terminal() and state.current_player() >= 0 else 0
        rows: list[list[str]] = []
        for raw_line in state.observation_string(observer).splitlines():
            cells: list[str] = []
            for char in raw_line:
                if char in {"x", "o"}:
                    cells.append(char)
                elif char in {"-", "."}:
                    cells.append(".")
            if len(cells) == expected_cols:
                rows.append(cells)
        if len(rows) != expected_rows:
            raise RuntimeError(
                f"Unable to parse {self.spec.variant_name} board: expected {expected_rows} rows, got {len(rows)}"
            )
        return rows

    def _board_planes(self, board: list[list[str]], *, current_player: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        own = np.zeros((self.spec.pad_h, self.spec.pad_w), dtype=np.float32)
        opp = np.zeros((self.spec.pad_h, self.spec.pad_w), dtype=np.float32)
        empty = np.zeros((self.spec.pad_h, self.spec.pad_w), dtype=np.float32)
        own_symbol = "x" if int(current_player) == 0 else "o"
        opp_symbol = "o" if own_symbol == "x" else "x"
        for row_index, row in enumerate(board):
            for col_index, cell in enumerate(row):
                if cell == own_symbol:
                    own[row_index, col_index] = 1.0
                elif cell == opp_symbol:
                    opp[row_index, col_index] = 1.0
                else:
                    empty[row_index, col_index] = 1.0
        return own, opp, empty

    def _phase_plane(self) -> np.ndarray:
        return np.zeros((self.spec.pad_h, self.spec.pad_w), dtype=np.float32)


class OthelloStateEncoder(ObservationStringEncoder):
    def encode(self, state) -> np.ndarray:
        current_player = self._canonical_current_player(state)
        board = self._parse_board_tokens(state, expected_rows=8, expected_cols=8)
        own, opp, empty = self._board_planes(board, current_player=current_player)
        valid_mask = np.ones((8, 8), dtype=np.float32)
        return np.stack([own, opp, empty, valid_mask, self._phase_plane()], axis=0)


class HexStateEncoder(ObservationStringEncoder):
    def encode(self, state) -> np.ndarray:
        current_player = self._canonical_current_player(state)
        board = self._parse_board_tokens(state, expected_rows=self.spec.board_h, expected_cols=self.spec.board_w)
        if self.spec.uses_transpose_canonicalization and current_player == 1:
            board = [list(row) for row in zip(*board)]
            board = [[{"x": "o", "o": "x"}.get(cell, cell) for cell in row] for row in board]
            current_player = 0
        own, opp, empty = self._board_planes(board, current_player=current_player)
        valid_mask = np.zeros((self.spec.pad_h, self.spec.pad_w), dtype=np.float32)
        valid_mask[: self.spec.board_h, : self.spec.board_w] = 1.0
        return np.stack([own, opp, empty, valid_mask, self._phase_plane()], axis=0)


class ClobberStateEncoder(ObservationStringEncoder):
    def encode(self, state) -> np.ndarray:
        current_player = self._canonical_current_player(state)
        board = self._parse_board_tokens(state, expected_rows=self.spec.board_h, expected_cols=self.spec.board_w)
        own, opp, empty = self._board_planes(board, current_player=current_player)
        valid_mask = np.zeros((self.spec.pad_h, self.spec.pad_w), dtype=np.float32)
        valid_mask[: self.spec.board_h, : self.spec.board_w] = 1.0
        return np.stack([own, opp, empty, valid_mask, self._phase_plane()], axis=0)


def build_state_encoder(spec: GameSpec) -> GameStateEncoder:
    family_builders = {
        "othello": OthelloStateEncoder,
        "hex": HexStateEncoder,
        "clobber": ClobberStateEncoder,
    }
    try:
        builder = family_builders[spec.family]
    except KeyError as exc:
        raise KeyError(f"No state encoder registered for family={spec.family}") from exc
    return builder(spec)
