from __future__ import annotations

from dataclasses import dataclass, field


TASK_ID_STRIDE = 100_000_000


@dataclass(frozen=True, slots=True)
class GameSpec:
    family: str
    variant_name: str
    task_id: int
    board_h: int
    board_w: int
    pad_h: int
    pad_w: int
    input_channels: int
    action_dim: int
    max_game_length: int
    uses_transpose_canonicalization: bool
    baseline_max_simulations: int
    baseline_n_rollouts: int
    game_name: str = ""
    game_params: dict[str, int | bool | str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        game_name = self.game_name or self.family
        object.__setattr__(self, "game_name", game_name)
        if self.board_h > self.pad_h or self.board_w > self.pad_w:
            raise ValueError(f"{self.variant_name}: board size cannot exceed padded size")
        if self.input_channels <= 0:
            raise ValueError("input_channels must be positive")
        if self.action_dim <= 0:
            raise ValueError("action_dim must be positive")
        if self.max_game_length <= 0:
            raise ValueError("max_game_length must be positive")

    @property
    def board_shape(self) -> tuple[int, int]:
        return self.board_h, self.board_w

    @property
    def padded_shape(self) -> tuple[int, int]:
        return self.pad_h, self.pad_w

    @property
    def observation_shape(self) -> tuple[int, int, int]:
        return self.input_channels, self.pad_h, self.pad_w

    @property
    def variant_index(self) -> int:
        return int(self.task_id % TASK_ID_STRIDE)

    @property
    def phase_denom(self) -> float:
        return float(max(self.max_game_length, 1))

    def phase_ratio(self, move_index: int) -> float:
        return min(max(float(move_index) / self.phase_denom, 0.0), 1.0)
