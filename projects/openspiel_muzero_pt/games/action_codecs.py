from __future__ import annotations

from math import floor
from typing import Protocol

import torch

from .game_spec import GameSpec


class ActionCodec(Protocol):
    def encode_dense(self, action: int, spec: GameSpec) -> int: ...

    def decode_dense(self, action_id: int, spec: GameSpec) -> int: ...

    def to_action_planes(self, action_id: int, spec: GameSpec, *, device: torch.device | None = None) -> torch.Tensor: ...

    def batch_action_planes(
        self,
        action_ids: torch.Tensor | list[int],
        spec: GameSpec,
        *,
        device: torch.device | None = None,
    ) -> torch.Tensor: ...

    def remap_under_symmetry(self, action_id: int, symmetry: str, spec: GameSpec) -> int: ...

    def remap_under_hex_transpose(self, action_id: int, spec: GameSpec) -> int: ...


def _cell_to_coords(index: int, width: int) -> tuple[int, int]:
    return divmod(int(index), int(width))


def _coords_to_cell(row: int, col: int, width: int) -> int:
    return int(row) * int(width) + int(col)


def _transform_square_coord(row: int, col: int, width: int, symmetry: str) -> tuple[int, int]:
    last = int(width) - 1
    if symmetry == "identity":
        return row, col
    if symmetry == "rot90":
        return col, last - row
    if symmetry == "rot180":
        return last - row, last - col
    if symmetry == "rot270":
        return last - col, row
    if symmetry == "flip_h":
        return row, last - col
    if symmetry == "flip_v":
        return last - row, col
    if symmetry == "diag":
        return col, row
    if symmetry == "anti_diag":
        return last - col, last - row
    raise KeyError(f"Unsupported symmetry: {symmetry}")


class OthelloActionCodec:
    pass_action = 64

    def encode_dense(self, action: int, spec: GameSpec) -> int:
        action = int(action)
        if not 0 <= action <= self.pass_action:
            raise ValueError(f"Othello action out of range: {action}")
        return action

    def decode_dense(self, action_id: int, spec: GameSpec) -> int:
        return self.encode_dense(action_id, spec)

    def to_action_planes(self, action_id: int, spec: GameSpec, *, device: torch.device | None = None) -> torch.Tensor:
        action_id = self.encode_dense(action_id, spec)
        planes = torch.zeros((3, spec.pad_h, spec.pad_w), dtype=torch.float32, device=device)
        if action_id == self.pass_action:
            planes[2].fill_(1.0)
            return planes
        row, col = _cell_to_coords(action_id, spec.board_w)
        planes[1, row, col] = 1.0
        return planes

    def batch_action_planes(
        self,
        action_ids: torch.Tensor | list[int],
        spec: GameSpec,
        *,
        device: torch.device | None = None,
    ) -> torch.Tensor:
        action_ids = torch.as_tensor(action_ids, dtype=torch.long, device=device).reshape(-1)
        planes = torch.zeros((action_ids.shape[0], 3, spec.pad_h, spec.pad_w), dtype=torch.float32, device=device)
        pass_mask = action_ids == self.pass_action
        if bool(pass_mask.any()):
            pass_ids = torch.nonzero(pass_mask, as_tuple=False).squeeze(-1)
            planes[pass_ids, 2, :, :] = 1.0
        move_mask = ~pass_mask
        if bool(move_mask.any()):
            move_ids = action_ids[move_mask]
            rows = torch.div(move_ids, spec.board_w, rounding_mode="floor")
            cols = torch.remainder(move_ids, spec.board_w)
            batch_ids = torch.nonzero(move_mask, as_tuple=False).squeeze(-1)
            planes[batch_ids, 1, rows, cols] = 1.0
        return planes

    def remap_under_symmetry(self, action_id: int, symmetry: str, spec: GameSpec) -> int:
        action_id = self.encode_dense(action_id, spec)
        if action_id == self.pass_action:
            return action_id
        row, col = _cell_to_coords(action_id, spec.board_w)
        new_row, new_col = _transform_square_coord(row, col, spec.board_w, symmetry)
        return _coords_to_cell(new_row, new_col, spec.board_w)

    def remap_under_hex_transpose(self, action_id: int, spec: GameSpec) -> int:
        return self.encode_dense(action_id, spec)


class HexActionCodec:
    def encode_dense(self, action: int, spec: GameSpec) -> int:
        action = int(action)
        if not 0 <= action < spec.board_h * spec.board_w:
            raise ValueError(f"Hex action out of range: {action}")
        return action

    def decode_dense(self, action_id: int, spec: GameSpec) -> int:
        return self.encode_dense(action_id, spec)

    def to_action_planes(self, action_id: int, spec: GameSpec, *, device: torch.device | None = None) -> torch.Tensor:
        action_id = self.encode_dense(action_id, spec)
        row, col = _cell_to_coords(action_id, spec.board_w)
        planes = torch.zeros((3, spec.pad_h, spec.pad_w), dtype=torch.float32, device=device)
        planes[1, row, col] = 1.0
        return planes

    def batch_action_planes(
        self,
        action_ids: torch.Tensor | list[int],
        spec: GameSpec,
        *,
        device: torch.device | None = None,
    ) -> torch.Tensor:
        action_ids = torch.as_tensor(action_ids, dtype=torch.long, device=device).reshape(-1)
        planes = torch.zeros((action_ids.shape[0], 3, spec.pad_h, spec.pad_w), dtype=torch.float32, device=device)
        rows = torch.div(action_ids, spec.board_w, rounding_mode="floor")
        cols = torch.remainder(action_ids, spec.board_w)
        batch_ids = torch.arange(action_ids.shape[0], device=action_ids.device)
        planes[batch_ids, 1, rows, cols] = 1.0
        return planes

    def remap_under_symmetry(self, action_id: int, symmetry: str, spec: GameSpec) -> int:
        action_id = self.encode_dense(action_id, spec)
        row, col = _cell_to_coords(action_id, spec.board_w)
        if symmetry == "identity":
            new_row, new_col = row, col
        elif symmetry == "diag":
            new_row, new_col = col, row
        elif symmetry == "rot180":
            last = spec.board_w - 1
            new_row, new_col = last - row, last - col
        else:
            raise KeyError(f"Unsupported Hex symmetry: {symmetry}")
        return _coords_to_cell(new_row, new_col, spec.board_w)

    def remap_under_hex_transpose(self, action_id: int, spec: GameSpec) -> int:
        action_id = self.encode_dense(action_id, spec)
        row, col = _cell_to_coords(action_id, spec.board_w)
        return _coords_to_cell(col, row, spec.board_w)


class ClobberActionCodec:
    direction_vectors = {
        0: (-1, 0),
        1: (0, 1),
        2: (1, 0),
        3: (0, -1),
    }
    inverse_vectors = {value: key for key, value in direction_vectors.items()}

    def encode_dense(self, action: int, spec: GameSpec) -> int:
        action = int(action)
        if not 0 <= action < spec.action_dim:
            raise ValueError(f"Clobber action out of range: {action}")
        return action

    def decode_dense(self, action_id: int, spec: GameSpec) -> int:
        return self.encode_dense(action_id, spec)

    def _decode_components(self, action_id: int, spec: GameSpec) -> tuple[int, int, int]:
        action_id = self.encode_dense(action_id, spec)
        square_index, direction = divmod(action_id, 4)
        row, col = _cell_to_coords(square_index, spec.board_w)
        return row, col, direction

    def _destination(self, row: int, col: int, direction: int) -> tuple[int, int]:
        delta_row, delta_col = self.direction_vectors[int(direction)]
        return row + delta_row, col + delta_col

    def _encode_components(self, row: int, col: int, direction: int, spec: GameSpec) -> int:
        return ((_coords_to_cell(row, col, spec.board_w)) * 4) + int(direction)

    def to_action_planes(self, action_id: int, spec: GameSpec, *, device: torch.device | None = None) -> torch.Tensor:
        row, col, direction = self._decode_components(action_id, spec)
        dst_row, dst_col = self._destination(row, col, direction)
        planes = torch.zeros((3, spec.pad_h, spec.pad_w), dtype=torch.float32, device=device)
        if 0 <= row < spec.board_h and 0 <= col < spec.board_w:
            planes[0, row, col] = 1.0
        if 0 <= dst_row < spec.board_h and 0 <= dst_col < spec.board_w:
            planes[1, dst_row, dst_col] = 1.0
        return planes

    def batch_action_planes(
        self,
        action_ids: torch.Tensor | list[int],
        spec: GameSpec,
        *,
        device: torch.device | None = None,
    ) -> torch.Tensor:
        action_ids = torch.as_tensor(action_ids, dtype=torch.long, device=device).reshape(-1)
        square_index = torch.div(action_ids, 4, rounding_mode="floor")
        direction = torch.remainder(action_ids, 4)
        row = torch.div(square_index, spec.board_w, rounding_mode="floor")
        col = torch.remainder(square_index, spec.board_w)
        delta_row = torch.tensor([-1, 0, 1, 0], dtype=torch.long, device=action_ids.device)[direction]
        delta_col = torch.tensor([0, 1, 0, -1], dtype=torch.long, device=action_ids.device)[direction]
        dst_row = row + delta_row
        dst_col = col + delta_col
        planes = torch.zeros((action_ids.shape[0], 3, spec.pad_h, spec.pad_w), dtype=torch.float32, device=device)
        batch_ids = torch.arange(action_ids.shape[0], device=action_ids.device)
        src_valid = (row >= 0) & (row < spec.board_h) & (col >= 0) & (col < spec.board_w)
        if bool(src_valid.any()):
            src_ids = batch_ids[src_valid]
            planes[src_ids, 0, row[src_valid], col[src_valid]] = 1.0
        dst_valid = (dst_row >= 0) & (dst_row < spec.board_h) & (dst_col >= 0) & (dst_col < spec.board_w)
        if bool(dst_valid.any()):
            dst_ids = batch_ids[dst_valid]
            planes[dst_ids, 1, dst_row[dst_valid], dst_col[dst_valid]] = 1.0
        return planes

    def remap_under_symmetry(self, action_id: int, symmetry: str, spec: GameSpec) -> int:
        row, col, direction = self._decode_components(action_id, spec)
        dst_row, dst_col = self._destination(row, col, direction)
        if symmetry == "identity":
            new_src = (row, col)
            new_dst = (dst_row, dst_col)
        elif symmetry == "flip_h":
            last = spec.board_w - 1
            new_src = (row, last - col)
            new_dst = (dst_row, last - dst_col)
        elif symmetry == "flip_v":
            last = spec.board_h - 1
            new_src = (last - row, col)
            new_dst = (last - dst_row, dst_col)
        elif symmetry == "rot180":
            last_h = spec.board_h - 1
            last_w = spec.board_w - 1
            new_src = (last_h - row, last_w - col)
            new_dst = (last_h - dst_row, last_w - dst_col)
        else:
            raise KeyError(f"Unsupported Clobber symmetry: {symmetry}")
        delta = (new_dst[0] - new_src[0], new_dst[1] - new_src[1])
        new_direction = self.inverse_vectors[delta]
        return self._encode_components(new_src[0], new_src[1], new_direction, spec)

    def remap_under_hex_transpose(self, action_id: int, spec: GameSpec) -> int:
        return self.encode_dense(action_id, spec)


_CODECS: dict[str, ActionCodec] = {
    "othello": OthelloActionCodec(),
    "hex": HexActionCodec(),
    "clobber": ClobberActionCodec(),
}


def get_action_codec(spec_or_family: GameSpec | str) -> ActionCodec:
    family = spec_or_family.family if isinstance(spec_or_family, GameSpec) else str(spec_or_family)
    return _CODECS[family]
